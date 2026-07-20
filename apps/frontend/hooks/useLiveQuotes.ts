"use client";

import { useEffect, useRef, useState } from "react";

export interface LiveQuote {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
}

/**
 * Subscribes to /ws/quotes for the given symbols. Reconnects automatically with
 * backoff if the connection drops (network blip, backend restart) — a raw
 * `new WebSocket()` with no reconnect logic is a common half-finished pattern this
 * deliberately avoids.
 */
export function useLiveQuotes(symbols: string[]) {
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);

  useEffect(() => {
    if (symbols.length === 0) return;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const token = localStorage.getItem("access_token");
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const backendHost = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${window.location.host}`;
      const url = `${backendHost}/ws/quotes?token=${token ?? ""}&symbols=${symbols.join(",")}`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        reconnectAttempt.current = 0;
      };

      ws.onmessage = (event) => {
        if (cancelled) return;
        try {
          const data = JSON.parse(event.data) as LiveQuote & { error?: string };
          if (data.error) return;
          setQuotes((prev) => ({ ...prev, [data.symbol]: data }));
        } catch {
          /* ignore malformed frame */
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        const delay = Math.min(1000 * 2 ** reconnectAttempt.current, 15000);
        reconnectAttempt.current += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols.join(",")]);

  return { quotes, connected };
}
