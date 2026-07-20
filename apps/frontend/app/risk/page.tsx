"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { riskApi, AccountRiskSummary } from "@/lib/api";
import { StatCard } from "@/components/StatCard";

export default function RiskDashboardPage() {
  const [summaries, setSummaries] = useState<AccountRiskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    riskApi
      .summary()
      .then(setSummaries)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load risk data"));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Risk Dashboard</h1>
        <p className="text-sm text-gray-500">
          Live open-position exposure and margin utilization per account
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          {error}
        </div>
      )}

      {summaries.length === 0 && !error && (
        <div className="rounded-lg border border-border bg-surface p-6 text-sm text-gray-400">
          No accounts connected yet.
        </div>
      )}

      {summaries.map((s) => (
        <div key={s.account_id} className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-300">Account {s.account_id.slice(0, 8)}</span>
            <span className={clsx("text-xs px-2 py-0.5 rounded", s.is_live ? "bg-bearish/10 text-bearish" : "bg-gray-500/10 text-gray-400")}>
              {s.is_live ? "LIVE" : "DEMO"}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Equity" value={`$${s.equity.toLocaleString()}`} />
            <StatCard
              label="Margin Utilization"
              value={s.margin_utilization_pct !== null ? `${s.margin_utilization_pct.toFixed(1)}%` : "No snapshot yet"}
            />
            <StatCard
              label="Unrealized PnL"
              value={`${s.total_unrealized_pnl >= 0 ? "+" : ""}${s.total_unrealized_pnl.toFixed(2)}`}
              deltaPositive={s.total_unrealized_pnl >= 0}
            />
            <StatCard label="Open Positions" value={String(s.open_position_count)} />
          </div>

          {s.exposures.length > 0 && (
            <div className="rounded-lg border border-border bg-surface overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 border-b border-border">
                    <th className="px-4 py-3">Symbol</th>
                    <th className="px-4 py-3">Net Exposure</th>
                    <th className="px-4 py-3">Gross Volume</th>
                    <th className="px-4 py-3">Positions</th>
                    <th className="px-4 py-3">Unrealized PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {s.exposures.map((e) => (
                    <tr key={e.symbol} className="border-b border-border last:border-0">
                      <td className="px-4 py-3 text-gray-100 font-medium">{e.symbol}</td>
                      <td
                        className={clsx(
                          "px-4 py-3",
                          e.net_volume > 0 ? "text-bullish" : e.net_volume < 0 ? "text-bearish" : "text-gray-400"
                        )}
                      >
                        {e.net_volume > 0 ? "+" : ""}
                        {e.net_volume.toFixed(2)} lots
                      </td>
                      <td className="px-4 py-3 text-gray-300">{e.gross_volume.toFixed(2)} lots</td>
                      <td className="px-4 py-3 text-gray-300">{e.position_count}</td>
                      <td
                        className={clsx(
                          "px-4 py-3 font-medium",
                          e.unrealized_pnl >= 0 ? "text-bullish" : "text-bearish"
                        )}
                      >
                        {e.unrealized_pnl >= 0 ? "+" : ""}
                        {e.unrealized_pnl.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
