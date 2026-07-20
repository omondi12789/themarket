"use client";

import { useEffect, useState } from "react";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { StatCard } from "@/components/StatCard";
import { tradingApi, AccountSummary } from "@/lib/api";

// Placeholder equity series shown before a real account is connected; replaced by
// live equity history once /accounts/{id}/equity-history is wired up (Phase 9 follow-up).
const SAMPLE_EQUITY = Array.from({ length: 30 }, (_, i) => ({
  day: i + 1,
  equity: 10000 * (1 + 0.002 * i + Math.sin(i / 4) * 0.01),
}));

export default function DashboardPage() {
  const [accounts, setAccounts] = useState<AccountSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    tradingApi
      .listAccounts()
      .then(setAccounts)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load accounts"));
  }, []);

  const totalEquity = accounts?.reduce((sum, a) => sum + a.equity, 0) ?? 0;
  const totalBalance = accounts?.reduce((sum, a) => sum + a.balance, 0) ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Dashboard</h1>
        <p className="text-sm text-gray-500">Account overview and performance</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Equity" value={`$${totalEquity.toLocaleString()}`} />
        <StatCard label="Total Balance" value={`$${totalBalance.toLocaleString()}`} />
        <StatCard label="Connected Accounts" value={String(accounts?.length ?? 0)} />
        <StatCard
          label="Status"
          value={error ? "Backend unreachable" : accounts ? "Live" : "Loading…"}
        />
      </div>

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          Couldn&apos;t load accounts from the backend: {error}. Connect a broker account under
          Settings once the backend is running.
        </div>
      )}

      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="text-sm text-gray-400 mb-3">Equity Curve</div>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={SAMPLE_EQUITY}>
            <CartesianGrid stroke="#1f2531" strokeDasharray="3 3" />
            <XAxis dataKey="day" stroke="#6b7280" fontSize={12} />
            <YAxis stroke="#6b7280" fontSize={12} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: "#11151f", border: "1px solid #1f2531" }} />
            <Line type="monotone" dataKey="equity" stroke="#3b82f6" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
