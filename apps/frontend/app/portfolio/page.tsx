"use client";

import { useEffect, useState } from "react";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { portfolioApi, tradingApi, EquityHistoryResponse, AccountSummary } from "@/lib/api";

export default function PortfolioPage() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [history, setHistory] = useState<EquityHistoryResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([tradingApi.listAccounts(), portfolioApi.equityHistory(30)])
      .then(([accs, hist]) => {
        setAccounts(accs);
        setHistory(hist);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "failed to load portfolio data");
        setLoading(false);
      });
  }, []);

  function accountLabel(accountId: string): string {
    const acc = accounts.find((a) => a.id === accountId);
    return acc ? `${acc.broker_type.toUpperCase()} · ${acc.broker_login}` : accountId.slice(0, 8);
  }

  // Merge each account's points onto a shared timeline for the multi-line chart.
  const timestamps = Array.from(
    new Set(history.flatMap((h) => h.points.map((p) => p.captured_at)))
  ).sort();
  const chartData = timestamps.map((ts) => {
    const row: Record<string, string | number> = { timestamp: new Date(ts).toLocaleString() };
    for (const h of history) {
      const point = h.points.find((p) => p.captured_at === ts);
      if (point) row[accountLabel(h.account_id)] = point.equity;
    }
    return row;
  });

  const colors = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#ef4444"];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Portfolio</h1>
        <p className="text-sm text-gray-500">Real equity history per connected account (15-min snapshots)</p>
      </div>

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          {error}
        </div>
      )}

      {!loading && accounts.length === 0 && !error && (
        <div className="rounded-lg border border-border bg-surface p-6 text-sm text-gray-400">
          No accounts connected yet. Connect one from Settings.
        </div>
      )}

      {chartData.length === 0 && accounts.length > 0 && !error && (
        <div className="rounded-lg border border-accent/20 bg-accent/5 p-4 text-sm text-gray-400">
          No equity snapshots yet — the scheduled task captures one every 15 minutes once an account
          is connected and the Celery beat/worker services are running.
        </div>
      )}

      {chartData.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={chartData}>
              <CartesianGrid stroke="#1f2531" strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" stroke="#6b7280" fontSize={11} minTickGap={40} />
              <YAxis stroke="#6b7280" fontSize={12} domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ background: "#11151f", border: "1px solid #1f2531" }} />
              <Legend />
              {history.map((h, i) => (
                <Line
                  key={h.account_id}
                  type="monotone"
                  dataKey={accountLabel(h.account_id)}
                  stroke={colors[i % colors.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {accounts.map((a) => (
          <div key={a.id} className="rounded-lg border border-border bg-surface p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-100">
                {a.broker_type.toUpperCase()} · {a.broker_login}
              </span>
              <span className={a.is_live ? "text-bearish text-xs" : "text-gray-500 text-xs"}>
                {a.is_live ? "LIVE" : "DEMO"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div className="text-xs text-gray-500">Balance</div>
                <div className="text-gray-200">
                  {a.balance.toLocaleString()} {a.currency}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Equity</div>
                <div className="text-gray-200">
                  {a.equity.toLocaleString()} {a.currency}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
