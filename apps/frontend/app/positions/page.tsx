"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { tradingApi, AccountSummary, PositionSummary } from "@/lib/api";

export default function PositionsPage() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [positions, setPositions] = useState<PositionSummary[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    tradingApi
      .listAccounts()
      .then((accs) => {
        setAccounts(accs);
        if (accs.length > 0) setSelectedAccount(accs[0].id);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "failed to load accounts");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedAccount) return;
    tradingApi
      .listPositions(selectedAccount)
      .then(setPositions)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load positions"));
  }, [selectedAccount]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Positions</h1>
        <p className="text-sm text-gray-500">Open positions across your connected accounts</p>
      </div>

      {accounts.length > 1 && (
        <select
          value={selectedAccount ?? ""}
          onChange={(e) => setSelectedAccount(e.target.value)}
          className="rounded-md bg-surface border border-border px-3 py-2 text-sm text-gray-100"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.broker_type.toUpperCase()} · {a.broker_login} ({a.currency})
            </option>
          ))}
        </select>
      )}

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          {error}
        </div>
      )}

      {!loading && accounts.length === 0 && !error && (
        <div className="rounded-lg border border-border bg-surface p-6 text-sm text-gray-400">
          No broker accounts connected yet. Connect one from Settings to see live positions here.
        </div>
      )}

      {positions.length > 0 && (
        <div className="rounded-lg border border-border bg-surface overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-border">
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">Side</th>
                <th className="px-4 py-3">Volume</th>
                <th className="px-4 py-3">Entry Price</th>
                <th className="px-4 py-3">Unrealized PnL</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 text-gray-100 font-medium">{p.symbol}</td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        p.side === "buy" ? "bg-bullish/10 text-bullish" : "bg-bearish/10 text-bearish"
                      )}
                    >
                      {p.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-300">{p.volume}</td>
                  <td className="px-4 py-3 text-gray-300">{p.entry_price}</td>
                  <td
                    className={clsx(
                      "px-4 py-3 font-medium",
                      p.unrealized_pnl >= 0 ? "text-bullish" : "text-bearish"
                    )}
                  >
                    {p.unrealized_pnl >= 0 ? "+" : ""}
                    {p.unrealized_pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
