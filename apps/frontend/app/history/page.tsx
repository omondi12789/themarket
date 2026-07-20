"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { ordersApi, OrderSummary } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  filled: "bg-bullish/10 text-bullish",
  submitted: "bg-accent/10 text-accent",
  pending: "bg-gray-500/10 text-gray-400",
  partially_filled: "bg-accent/10 text-accent",
  cancelled: "bg-gray-500/10 text-gray-400",
  rejected: "bg-bearish/10 text-bearish",
};

export default function HistoryPage() {
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ordersApi
      .list()
      .then(setOrders)
      .catch((err) => setError(err instanceof Error ? err.message : "failed to load order history"));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Trade History</h1>
        <p className="text-sm text-gray-500">Every order placed across your connected accounts</p>
      </div>

      {error && (
        <div className="rounded-lg border border-bearish/30 bg-bearish/5 p-4 text-sm text-bearish">
          {error}
        </div>
      )}

      {orders.length === 0 && !error && (
        <div className="rounded-lg border border-border bg-surface p-6 text-sm text-gray-400">
          No orders yet. Place your first trade from the Trading Terminal.
        </div>
      )}

      {orders.length > 0 && (
        <div className="rounded-lg border border-border bg-surface overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-border">
                <th className="px-4 py-3">Symbol</th>
                <th className="px-4 py-3">Side</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Volume</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Broker Order ID</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 text-gray-100 font-medium">{o.symbol}</td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        o.side === "buy" ? "bg-bullish/10 text-bullish" : "bg-bearish/10 text-bearish"
                      )}
                    >
                      {o.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-300">{o.order_type}</td>
                  <td className="px-4 py-3 text-gray-300">{o.volume}</td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        STATUS_COLORS[o.status] ?? "bg-gray-500/10 text-gray-400"
                      )}
                    >
                      {o.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 font-mono text-xs">
                    {o.broker_order_id ?? "—"}
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
