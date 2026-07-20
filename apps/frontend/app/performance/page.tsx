"use client";

import { useEffect, useState } from "react";
import { portfolioApi, tradingApi, PerformanceResponse, AccountSummary } from "@/lib/api";
import { StatCard } from "@/components/StatCard";

export default function PerformancePage() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [performance, setPerformance] = useState<PerformanceResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([tradingApi.listAccounts(), portfolioApi.performance(30)])
      .then(([accs, perf]) => {
        setAccounts(accs);
        setPerformance(perf);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load performance data"));
  }, []);

  function accountLabel(accountId: string): string {
    const acc = accounts.find((a) => a.id === accountId);
    return acc ? `${acc.broker_type.toUpperCase()} · ${acc.broker_login}` : accountId.slice(0, 8);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Performance Analytics</h1>
        <p className="text-sm text-gray-500">
          Sharpe, Sortino, Calmar, drawdown, VaR &amp; CVaR — computed from real equity snapshot history
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          {error}
        </div>
      )}

      {performance.length === 0 && !error && (
        <div className="rounded-lg border border-border bg-surface p-6 text-sm text-gray-400">
          No accounts connected yet, or no performance data available.
        </div>
      )}

      {performance.map((p) => (
        <div key={p.account_id} className="space-y-3">
          <div className="text-sm font-medium text-gray-300">{accountLabel(p.account_id)}</div>

          {p.metrics === null ? (
            <div className="rounded-lg border border-accent/20 bg-accent/5 p-4 text-sm text-gray-400">
              {p.note}
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard label="Sharpe Ratio" value={p.metrics.sharpe_ratio.toFixed(2)} />
              <StatCard label="Sortino Ratio" value={p.metrics.sortino_ratio.toFixed(2)} />
              <StatCard label="Calmar Ratio" value={p.metrics.calmar_ratio.toFixed(2)} />
              <StatCard
                label="Max Drawdown"
                value={`${(p.metrics.max_drawdown * 100).toFixed(2)}%`}
                deltaPositive={false}
              />
              <StatCard label="VaR (95%)" value={`${(p.metrics.var_95 * 100).toFixed(2)}%`} />
              <StatCard label="CVaR (95%)" value={`${(p.metrics.cvar_95 * 100).toFixed(2)}%`} />
              <StatCard
                label="Total Return"
                value={`${(p.metrics.total_return * 100).toFixed(2)}%`}
                deltaPositive={p.metrics.total_return >= 0}
              />
              <StatCard
                label="Volatility (ann.)"
                value={`${(p.metrics.volatility_annualized * 100).toFixed(2)}%`}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
