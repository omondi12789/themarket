"use client";

import { useState } from "react";

interface OrderTicketProps {
  symbol: string;
  onSymbolChange: (symbol: string) => void;
}

const SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"];

export function OrderTicket({ symbol, onSymbolChange }: OrderTicketProps) {
  const [volume, setVolume] = useState("0.10");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function placeOrder(side: "buy" | "sell") {
    setSubmitting(true);
    setMessage(null);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch("/api/backend/orders", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          symbol,
          side,
          order_type: "market",
          volume: parseFloat(volume),
          stop_loss: stopLoss ? parseFloat(stopLoss) : null,
          take_profit: takeProfit ? parseFloat(takeProfit) : null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `order failed (${res.status})`);
      }
      setMessage(`${side.toUpperCase()} order submitted`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "order failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4 space-y-4">
      <div>
        <label className="block text-xs text-gray-400 mb-1">Symbol</label>
        <select
          value={symbol}
          onChange={(e) => onSymbolChange(e.target.value)}
          className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">Volume (lots)</label>
        <input
          type="number"
          step="0.01"
          min="0.01"
          value={volume}
          onChange={(e) => setVolume(e.target.value)}
          className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Stop Loss</label>
          <input
            type="number"
            step="0.00001"
            value={stopLoss}
            onChange={(e) => setStopLoss(e.target.value)}
            placeholder="optional"
            className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Take Profit</label>
          <input
            type="number"
            step="0.00001"
            value={takeProfit}
            onChange={(e) => setTakeProfit(e.target.value)}
            placeholder="optional"
            className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 pt-2">
        <button
          onClick={() => placeOrder("buy")}
          disabled={submitting}
          className="rounded-md bg-bullish py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Buy
        </button>
        <button
          onClick={() => placeOrder("sell")}
          disabled={submitting}
          className="rounded-md bg-bearish py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Sell
        </button>
      </div>

      {message && <div className="text-xs text-gray-400">{message}</div>}
    </div>
  );
}
