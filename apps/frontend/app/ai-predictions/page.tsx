"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { predictionsApi, Prediction, rlApi, RLSuggestion } from "@/lib/api";
import { StatCard } from "@/components/StatCard";

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"];

export default function AiPredictionsPage() {
  const [symbol, setSymbol] = useState("EURUSD");
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [accuracy, setAccuracy] = useState<{ evaluated_count: number; accuracy: number | null } | null>(
    null
  );
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rlSuggestion, setRlSuggestion] = useState<RLSuggestion | null>(null);
  const [rlTraining, setRlTraining] = useState(false);
  const [rlError, setRlError] = useState<string | null>(null);

  function loadHistory() {
    predictionsApi
      .list(symbol)
      .then(setPredictions)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load predictions"));
    predictionsApi
      .accuracy(symbol)
      .then(setAccuracy)
      .catch(() => setAccuracy(null));
  }

  useEffect(loadHistory, [symbol]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      await predictionsApi.generate(symbol);
      loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "prediction failed");
    } finally {
      setGenerating(false);
    }
  }

  async function handleTrainRL() {
    setRlTraining(true);
    setRlError(null);
    try {
      await rlApi.train(symbol);
      const suggestion = await rlApi.suggestSize(symbol);
      setRlSuggestion(suggestion);
    } catch (err) {
      setRlError(err instanceof Error ? err.message : "RL training failed");
    } finally {
      setRlTraining(false);
    }
  }

  async function handleSuggestSize() {
    setRlError(null);
    try {
      const suggestion = await rlApi.suggestSize(symbol);
      setRlSuggestion(suggestion);
    } catch (err) {
      setRlError(err instanceof Error ? err.message : "no trained agent yet — train first");
    }
  }

  const latest = predictions[0];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">AI Predictions</h1>
          <p className="text-sm text-gray-500">
            LightGBM directional classifier, trained per symbol on the quant feature pipeline
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded-md bg-surface border border-border px-3 py-2 text-sm text-gray-100"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {generating ? "Training & predicting…" : "Generate prediction"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          {error}
          {error.includes("backfill") && (
            <div className="mt-1 text-xs text-gray-500">
              This symbol needs historical bars in TimescaleDB first — the scheduled backfill job
              handles this automatically once running, or trigger it manually.
            </div>
          )}
        </div>
      )}

      {latest && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Latest Direction"
            value={latest.direction.toUpperCase()}
            delta={`${(latest.probability_up * 100).toFixed(1)}% prob. up`}
            deltaPositive={latest.direction === "up"}
          />
          <StatCard label="Confidence" value={`${(latest.confidence * 100).toFixed(1)}%`} />
          <StatCard label="CV Accuracy (train)" value={`${(latest.cv_accuracy_mean * 100).toFixed(1)}%`} />
          <StatCard
            label="Live Accuracy"
            value={
              accuracy && accuracy.accuracy !== null
                ? `${(accuracy.accuracy * 100).toFixed(1)}%`
                : "Not evaluated yet"
            }
            delta={accuracy ? `${accuracy.evaluated_count} evaluated` : undefined}
          />
        </div>
      )}

      <div className="rounded-lg border border-accent/20 bg-accent/5 p-4 text-xs text-gray-400">
        Cross-validated accuracy is measured with time-series splitting (no look-ahead) on
        historical data, but is not a guarantee of future performance. Treat predictions as one
        weighted input alongside quant signals and risk checks, not a standalone trade trigger.
      </div>

      {latest?.model_breakdown && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-sm text-gray-300 mb-3">Ensemble breakdown</div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-xs text-gray-500">LightGBM P(up)</div>
              <div className="text-gray-100">{(latest.model_breakdown.lightgbm_probability_up * 100).toFixed(1)}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">XGBoost P(up)</div>
              <div className="text-gray-100">{(latest.model_breakdown.xgboost_probability_up * 100).toFixed(1)}%</div>
            </div>
          </div>
        </div>
      )}

      {latest?.top_features && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="text-sm text-gray-300 mb-3">Top features driving this prediction</div>
          <div className="space-y-2">
            {Object.entries(latest.top_features)
              .slice(0, 8)
              .map(([name, importance]) => (
                <div key={name} className="flex items-center gap-3">
                  <div className="w-40 text-xs text-gray-400 truncate">{name}</div>
                  <div className="flex-1 h-2 bg-background rounded overflow-hidden">
                    <div
                      className="h-full bg-accent"
                      style={{ width: `${Math.min(importance * 400, 100)}%` }}
                    />
                  </div>
                  <div className="w-12 text-xs text-gray-500 text-right">{(importance * 100).toFixed(1)}%</div>
                </div>
              ))}
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm text-gray-300">RL Position Sizing Agent</div>
            <div className="text-xs text-gray-500">
              DQN agent, trained per symbol — suggests how much size (0-100%) to allocate to the
              EMA-trend direction, not a direction call itself
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={handleSuggestSize}
              className="rounded-md border border-border px-3 py-1.5 text-xs text-gray-300 hover:text-gray-100"
            >
              Get suggestion
            </button>
            <button
              onClick={handleTrainRL}
              disabled={rlTraining}
              className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
            >
              {rlTraining ? "Training (slow)…" : "Train agent"}
            </button>
          </div>
        </div>

        {rlError && <div className="text-xs text-bearish mb-2">{rlError}</div>}

        {rlSuggestion && (
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-gray-500">Suggested Size</div>
              <div className="text-lg text-gray-100">{(rlSuggestion.suggested_size * 100).toFixed(0)}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Confidence</div>
              <div className="text-lg text-gray-100">{(rlSuggestion.confidence * 100).toFixed(0)}%</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Agent Trained</div>
              <div className="text-sm text-gray-300">{new Date(rlSuggestion.agent_trained_at).toLocaleString()}</div>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-border">
              <th className="px-4 py-3">As Of</th>
              <th className="px-4 py-3">Direction</th>
              <th className="px-4 py-3">Prob. Up</th>
              <th className="px-4 py-3">Confidence</th>
              <th className="px-4 py-3">Model</th>
            </tr>
          </thead>
          <tbody>
            {predictions.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-500">
                  No predictions yet for {symbol}. Click &quot;Generate prediction&quot; above.
                </td>
              </tr>
            ) : (
              predictions.map((p) => (
                <tr key={p.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 text-gray-300">{new Date(p.as_of).toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        p.direction === "up" ? "bg-bullish/10 text-bullish" : "bg-bearish/10 text-bearish"
                      )}
                    >
                      {p.direction.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-300">{(p.probability_up * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-gray-300">{(p.confidence * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{p.model_type}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
