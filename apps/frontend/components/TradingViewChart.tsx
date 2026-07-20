"use client";

import { useEffect, useRef } from "react";

interface TradingViewChartProps {
  symbol?: string; // e.g. "FX:EURUSD"
  interval?: string; // e.g. "15", "60", "D"
  theme?: "dark" | "light";
  height?: number;
}

/**
 * Embeds TradingView's real "Advanced Real-Time Chart" widget via their public
 * embed script (no API key required for the free embeddable widget). This is the
 * standard, TradingView-sanctioned way to get professional charting without
 * building candlestick rendering from scratch.
 * Docs: https://www.tradingview.com/widget/advanced-chart/
 */
export function TradingViewChart({
  symbol = "FX:EURUSD",
  interval = "15",
  theme = "dark",
  height = 560,
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = "";

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: "Etc/UTC",
      theme,
      style: "1",
      locale: "en",
      enable_publishing: false,
      allow_symbol_change: true,
      hide_side_toolbar: false,
      studies: ["MASimple@tv-basicstudies", "RSI@tv-basicstudies"],
      support_host: "https://www.tradingview.com",
    });

    containerRef.current.appendChild(script);
  }, [symbol, interval, theme]);

  return (
    <div className="rounded-lg border border-border bg-surface overflow-hidden" style={{ height }}>
      <div ref={containerRef} className="tradingview-widget-container h-full w-full" />
    </div>
  );
}
