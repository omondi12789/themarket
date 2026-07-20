"use client";

import { useState } from "react";
import { TradingViewChart } from "@/components/TradingViewChart";
import { OrderTicket } from "@/components/OrderTicket";
import { useLiveQuotes } from "@/hooks/useLiveQuotes";

export default function TerminalPage() {
  const [symbol, setSymbol] = useState("EURUSD");
  const { quotes, connected } = useLiveQuotes([symbol]);
  const quote = quotes[symbol];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Trading Terminal</h1>
          <p className="text-sm text-gray-500">Live chart and order execution</p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className={connected ? "text-bullish" : "text-gray-500"}>
            {connected ? "● live" : "○ connecting…"}
          </span>
          {quote && (
            <span className="font-mono text-gray-300">
              <span className="text-bearish">{quote.bid.toFixed(5)}</span>
              {" / "}
              <span className="text-bullish">{quote.ask.toFixed(5)}</span>
              <span className="text-gray-500 ml-2">{(quote.spread * 10000).toFixed(1)} pips</span>
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3">
          <TradingViewChart symbol={`FX:${symbol}`} />
        </div>
        <div>
          <OrderTicket symbol={symbol} onSymbolChange={setSymbol} />
        </div>
      </div>
    </div>
  );
}
