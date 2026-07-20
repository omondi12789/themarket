# MT4/MT5 Connectivity — Comparison & Selection

Real options only, ranked by the spec's priority order, evaluated on latency, cost,
rate limits, scalability, and security.

## 1. Official `MetaTrader5` Python package

- **Cost:** Free.
- **How it works:** Direct IPC bridge to a *running* MT5 terminal on the same machine.
- **Platform:** Windows only — no official Linux/macOS build. To run in this repo's
  Docker/Linux stack, it needs a Windows VPS or VM (or Wine, unsupported/fragile).
- **Latency:** Lowest of the real options — local IPC + your broker's own server
  latency. No extra network hop.
- **Rate limits:** None imposed by the package itself; you're bound by your broker's
  server-side limits.
- **Scalability:** One terminal instance per account login; running many accounts
  means many terminal processes — heavier to scale horizontally than a cloud API.
- **Security:** Credentials only ever touch your own host; no third party in the loop.
- **Verdict:** Best choice for a single live account run from a Windows VPS you
  control — which is why the factory prefers it when configured and available.

## 2. MetaApi Cloud

- **Cost:** Free tier exists but is limited (small number of accounts, request-rate
  caps) — current numbers change, check metaapi.cloud/pricing before depending on
  specific limits. Paid tiers remove those caps.
- **How it works:** MetaApi hosts the MT4/MT5 terminal for you and exposes it over a
  REST/WebSocket API + official Python SDK (`metaapi-cloud-sdk`).
- **Platform:** Works from anywhere — Linux containers, serverless, this repo's
  Docker stack — since there's no local terminal dependency.
- **Latency:** Higher than local MT5 — your request travels to MetaApi's cloud, then
  to the broker. Fine for swing/position/portfolio strategies; a real cost for
  sub-second scalping.
- **Rate limits:** Enforced by MetaApi per plan tier (requests/min, concurrent
  accounts). Production scale requires a paid plan.
- **Scalability:** Designed for multi-account — this is its actual strength over the
  official package.
- **Security:** Broker credentials are held by MetaApi's cloud, not your infra —
  acceptable for most users, but it is a third party in the trust chain; read their
  security docs before connecting a live funded account.
- **Verdict:** The right fallback for any non-Windows deployment, and the better
  choice for multi-account/multi-strategy scaling regardless of OS.

## 3. Other bridges (Tonpo, open-source ZeroMQ/REST bridges to MT4/MT5)

- Free/open-source options exist but are community-maintained, with inconsistent
  reliability, security review, and MT5-build compatibility. Treated as a last-resort,
  self-hosted alternative — not implemented in this repo v1 because MT5 (official) +
  MetaApi already cover "cheapest local" and "cheapest cloud" without unaudited
  third-party middleware sitting between this platform and your funded account.

## Bottom line

There is **no completely free, official, unlimited-scale MT5 cloud API**. The
practical free path is: official package + your own Windows host (free but
single-machine and Windows-only), or MetaApi's limited free tier (free but capped).
This repo implements both behind one interface (`app/brokers/base.py`) and picks
automatically via `app/brokers/factory.py` based on what's configured — see that file
for the exact decision order.
