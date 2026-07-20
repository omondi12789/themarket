"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/authStore";

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const loading = useAuthStore((s) => s.loading);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password, totpCode || undefined);
      router.push("/");
    } catch (err) {
      const message = err instanceof Error ? err.message : "login failed";
      if (message.toLowerCase().includes("2fa")) {
        setNeedsTotp(true);
      }
      setError(message);
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-24">
      <h1 className="text-lg font-semibold text-gray-100 mb-1">Sign in</h1>
      <p className="text-sm text-gray-500 mb-6">THEMARKET AI Quant Forex</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md bg-surface border border-border px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Password</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md bg-surface border border-border px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent"
          />
        </div>

        {needsTotp && (
          <div>
            <label className="block text-xs text-gray-400 mb-1">2FA code</label>
            <input
              type="text"
              inputMode="numeric"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              className="w-full rounded-md bg-surface border border-border px-3 py-2 text-sm text-gray-100 outline-none focus:border-accent"
              placeholder="6-digit code"
            />
          </div>
        )}

        {error && <div className="text-xs text-bearish">{error}</div>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-accent py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
