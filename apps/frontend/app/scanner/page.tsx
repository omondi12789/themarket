"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { scannerApi, ScanResult } from "@/lib/api";

const SIGNAL_STYLES: Record<string, string> = {
  overbought: "bg-bearish/10 text-bearish",
  oversold: "bg-bullish/10 text-bullish",
  trending_up: "bg-bullish/10 text-bullish",
  trending_down: "bg-bearish/10 text-bearish",
  neutral: "bg-gray-500/10 text-gray-400",
  no_data: "bg-gray-500/10 text-gray-500",
};

export default function ScannerPage() {
  const [results, setResults] = useState<ScanResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function runScan() {
    setLoading(true);
    setError(null);
    scannerApi
      .scan()
      .then(setResults)
      .catch((err) => setError(err instanceof Error ? err.message : "scan failed"))
      .finally(() => setLoading(false));
  }

  useEffect(runScan, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Market Scanner</h1>
          <p className="text-sm text-gray-500">
            RSI/ADX/trend classification from the live quant feature pipeline — transparent rules,
            not a black-box score
          </p>
        </div>
        <button
          onClick={runScan}
          disabled={loading}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Scanning…" : "Rescan"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          {error}
        </div>
      )}

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-border">
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Signal</th>
              <th className="px-4 py-3">RSI (14)</th>
              <th className="px-4 py-3">ADX</th>
              <th className="px-4 py-3">Price vs SMA20</th>
              <th className="px-4 py-3">BB Position</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.symbol} className="border-b border-border last:border-0">
                <td className="px-4 py-3 text-gray-100 font-medium">{r.symbol}</td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "px-2 py-0.5 rounded text-xs font-medium",
                      SIGNAL_STYLES[r.signal] ?? SIGNAL_STYLES.neutral
                    )}
                  >
                    {r.signal.replace("_", " ")}
                  </span>
                  {r.note && <div className="text-xs text-gray-600 mt-1">{r.note}</div>}
                </td>
                <td className="px-4 py-3 text-gray-300">{r.rsi_14?.toFixed(1) ?? "—"}</td>
                <td className="px-4 py-3 text-gray-300">{r.adx?.toFixed(1) ?? "—"}</td>
                <td className="px-4 py-3 text-gray-300">
                  {r.price_vs_sma20_pct !== null ? `${r.price_vs_sma20_pct.toFixed(2)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-gray-300">{r.bb_position?.toFixed(2) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
