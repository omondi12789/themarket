"use client";

import { useEffect, useState } from "react";
import { tradingApi, AccountSummary } from "@/lib/api";

export default function SettingsPage() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [brokerType, setBrokerType] = useState<"mt5" | "mt4" | "metaapi">("mt5");
  const [brokerLogin, setBrokerLogin] = useState("");
  const [brokerServer, setBrokerServer] = useState("");
  const [brokerPassword, setBrokerPassword] = useState("");
  const [isLive, setIsLive] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function loadAccounts() {
    tradingApi.listAccounts().then(setAccounts).catch(() => {});
  }

  useEffect(loadAccounts, []);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch("/api/backend/accounts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          broker_type: brokerType,
          broker_login: brokerLogin,
          broker_server: brokerServer,
          broker_password: brokerPassword,
          is_live: isLive,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `connect failed (${res.status})`);
      }
      setMessage("Account connected.");
      setBrokerLogin("");
      setBrokerServer("");
      setBrokerPassword("");
      loadAccounts();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "connect failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-gray-100">Settings</h1>
        <p className="text-sm text-gray-500">Broker connections and account management</p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="text-sm text-gray-300 mb-3">Connected accounts</div>
        {accounts.length === 0 ? (
          <div className="text-sm text-gray-500">No accounts connected yet.</div>
        ) : (
          <div className="space-y-2">
            {accounts.map((a) => (
              <div
                key={a.id}
                className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <span className="text-gray-200">
                  {a.broker_type.toUpperCase()} · {a.broker_login} @ {a.broker_login}
                </span>
                <span className={a.is_live ? "text-bearish" : "text-gray-500"}>
                  {a.is_live ? "LIVE" : "DEMO"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <form onSubmit={handleConnect} className="rounded-lg border border-border bg-surface p-4 space-y-4">
        <div className="text-sm text-gray-300">Connect a broker account</div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Broker type</label>
          <select
            value={brokerType}
            onChange={(e) => setBrokerType(e.target.value as typeof brokerType)}
            className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
          >
            <option value="mt5">MT5 (official terminal — Windows host required)</option>
            <option value="metaapi">MetaApi Cloud (works from any host)</option>
            <option value="mt4">MT4</option>
          </select>
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">
            {brokerType === "metaapi" ? "MetaApi account ID" : "Login"}
          </label>
          <input
            required
            value={brokerLogin}
            onChange={(e) => setBrokerLogin(e.target.value)}
            className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
          />
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Server</label>
          <input
            required
            value={brokerServer}
            onChange={(e) => setBrokerServer(e.target.value)}
            placeholder="e.g. Broker-Live01"
            className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
          />
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">Password</label>
          <input
            required
            type="password"
            value={brokerPassword}
            onChange={(e) => setBrokerPassword(e.target.value)}
            className="w-full rounded-md bg-background border border-border px-3 py-2 text-sm text-gray-100"
          />
          <p className="text-xs text-gray-500 mt-1">
            Encrypted before storage (Fernet). Never stored or transmitted in plaintext.
          </p>
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-300">
          <input type="checkbox" checked={isLive} onChange={(e) => setIsLive(e.target.checked)} />
          This is a live account (real money)
        </label>

        {message && <div className="text-xs text-gray-400">{message}</div>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {submitting ? "Connecting…" : "Connect account"}
        </button>
      </form>
    </div>
  );
}
