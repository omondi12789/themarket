# Build Progress

Legend: ✅ done · 🔧 in progress · ⬜ not started

## Phase 1 — Scaffold
- ✅ Monorepo layout
- ✅ README
- ✅ docker-compose (postgres, timescaledb, redis, backend, ai-engine, frontend)
- ✅ .env.example
- ⬜ CI pipeline (lint/test/build)

## Phase 2 — Backend core
- ✅ FastAPI app skeleton + settings + health check
- ✅ DB models (users, trading_accounts, orders, positions)
- ✅ Alembic migrations (initial schema, hand-verified against models)
- ✅ Auth (JWT + refresh + 2FA/TOTP) — register/login/refresh/me + TOTP enroll/verify
- ✅ RBAC (require_role dependency factory; trader/admin/compliance/support)
- ✅ Broker abstraction interface (app/brokers/base.py)

## Phase 3 — MT4/MT5 integration
- ✅ MetaTrader5 Python package adapter (local terminal, free, Windows-only)
- ✅ MetaApi Cloud adapter (works from Linux/containers, capped free tier)
- ✅ Adapter comparison doc (docs/broker-comparison.md) + auto-selection factory
- ⬜ Live account connection endpoint (wire TradingAccount model + encrypted creds to factory)

## Phase 4 — Market data
- ✅ Data provider clients (Polygon, TwelveData, Finnhub) — real REST endpoints, documented free-tier limits
- ✅ TimescaleDB ingestion + hypertables (ohlcv_bars + ticks, compression + retention policies)
- ✅ Historical backfill job with automatic provider failover and idempotent upsert

## Phase 5 — Quant/math engine
- ✅ Technical indicators library (SMA, EMA, RSI, MACD, ATR, ADX, VWAP, Bollinger, Ichimoku, Fibonacci)
- ✅ Statistical models — Kalman filter (trend + dynamic hedge ratio), HMM regime detection, GARCH(1,1) volatility
- ✅ Stat-arb toolkit — correlation matrix, PCA factor model, Engle-Granger cointegration, z-score mean reversion
- ✅ Math toolkit — Monte Carlo (GBM + bootstrap robustness), FFT dominant cycle, wavelet denoise, entropy, Hurst exponent
- ✅ Risk metrics — Sharpe, Sortino, Calmar, max drawdown, VaR, CVaR, Kelly/fractional Kelly (formulas hand-verified)

## Phase 6 — AI engine
- ✅ HF model discovery/benchmark harness (scores task-relevance, license, adoption, size, measured latency; penalizes domain-mismatched general NLP models)
- ✅ Feature engineering pipeline (technical + price-action + regime features, aligned matrix)
- ✅ Smart Money Concepts detectors (swing points, BOS/CHOCH, fair value gaps, order blocks, liquidity zones)
- ✅ AI engine FastAPI service (/features/build, /risk/summary, /models/select-best) + Dockerfile

## Phase 7 — Scalping/execution engine
- ✅ Position sizing (volatility/ATR-scaled + Kelly-confidence-adjusted) + dynamic ATR stop/TP — hand-verified math
- ✅ Risk guards: daily loss limit, max trades/day, session filter (Sydney/Tokyo/London/NY), news blackout, spread filter
- ✅ Execution engine: latency + slippage measurement, trailing stop, break-even trigger, partial close
- ✅ Scalping orchestrator tying sizing + risk guards + execution together end-to-end

## Phase 8 — Backtesting
- ✅ Historical replay engine — bar-by-bar (no look-ahead), realistic spread/slippage cost model, intrabar SL/TP detection
- ✅ Walk-forward optimizer — rolling train/test windows, out-of-sample-only reporting
- ✅ Monte Carlo robustness testing (bootstrap resampling), exposed via ai-engine /backtest/robustness

## Phase 2 addendum — Accounts & Orders API (built to support the frontend)
- ✅ Broker credential encryption at rest (Fernet, app/core/crypto.py)
- ✅ POST/GET /api/accounts — connect a broker account, list accounts, list open positions
- ✅ POST/GET /api/orders — places a real order through the account's live broker adapter, persists status

## Phase 9 — Frontend
- ✅ Next.js 14 app shell (App Router, Tailwind, TypeScript) + sidebar nav
- ✅ Auth (login page + Zustand store, JWT stored client-side, 2FA-aware login flow)
- ✅ Trading terminal — real TradingView Advanced Chart embed + order ticket (buy/sell, SL/TP)
- ✅ Dashboard — account equity/balance stat cards + equity curve chart, wired to /api/accounts
- ⬜ Portfolio/positions/history/AI-predictions/scanner/risk/performance/settings pages (scaffolded in nav, not yet built)

## Phase 10 — Security/deploy
- ✅ Rate limiting (Redis-backed, tighter limits on /auth/login and /auth/register) + security headers (CSP, HSTS, X-Frame-Options, etc.)
- ✅ Audit log (append-only table + helper, wired into live order placement)
- ✅ Broker credential encryption at rest (Fernet)
- ✅ CI pipeline (.github/workflows/ci.yml — lint/build for backend, ai-engine, frontend + Docker image builds)
- ✅ Monitoring — Prometheus /metrics on the backend (request counts/latency, order counts, broker errors) + Prometheus/Grafana compose overlay

## Testing
- ✅ Backend: 17 real tests for sizing.py + risk_guard.py — pure-stdlib (Decimal/dataclasses/datetime),
  actually executed in this environment (no deps needed) and confirmed passing: 17/17.
- ✅ AI engine: tests for risk/metrics.py (Kelly, Sharpe, Sortino, VaR, CVaR, drawdown, Calmar) and
  indicators/technical.py (SMA/EMA/RSI/MACD/ATR/Bollinger/Fibonacci), verified against hand-computable
  edge cases (monotonic series, constant series, known drawdown). Needs numpy/pandas installed to run
  (no network in this build environment) — syntax-verified only here; run `pytest -v` locally.
- ✅ CI now hard-fails on the pure-stdlib backend suite and the ai-engine risk/indicator suite;
  broader integration tests (need live Postgres/Redis/heavier ML deps) remain advisory until DB
  fixtures are added.
- ⬜ No test coverage yet for: brokers (mt5/metaapi adapters — need mocked SDKs), auth endpoints
  (need a test DB), backtest engine, execution engine, smart_money pattern detectors.

## Known gaps / honest TODOs
- Frontend nav pages not yet built: Portfolio, AI Predictions, Market Scanner, Risk Dashboard,
  Performance Analytics. These need backend analytics endpoints designed first (e.g. equity history
  snapshots, per-strategy PnL attribution) — intentionally not faked with placeholder data.
- No live account equity-history snapshot job yet, so the dashboard's equity curve is illustrative,
  not real — needs a scheduled job writing to a new `equity_snapshots` table.
- No Celery worker wiring yet for scheduled jobs (backfill, model retraining, equity snapshots) —
  Celery is in requirements.txt but no worker/beat service exists in docker-compose yet.

## Phase 11 — Celery workers, equity snapshots, AI Predictions (this round)
- ✅ Celery app + worker + beat services wired into docker-compose (hourly backfill, 15-min equity snapshots)
- ✅ EquitySnapshot model/migration + task pulling real account_info from each connected broker
- ✅ /api/portfolio/equity-history — real (non-fabricated) equity curve data for the dashboard/performance pages
- ✅ DirectionalForecaster (ai-engine) — LightGBM classifier on the feature pipeline, TimeSeriesSplit
  cross-validation (no look-ahead), per-symbol model cache with staleness-based retraining
- ✅ /predictions/generate (ai-engine, stateless compute) + /api/predictions (backend: pulls real
  TimescaleDB bars, calls ai-engine, persists to a Prediction table for later accuracy auditing)
- ✅ /api/predictions/accuracy — honest: returns evaluated_count=0 rather than a fake number until
  an evaluation job (not yet built) back-fills `was_correct` against realized price moves
- ✅ Frontend AI Predictions page — generate on demand, prediction history table, live vs. train accuracy
- ⬜ Evaluation job to populate Prediction.was_correct (needs a scheduled task comparing each
  prediction's `as_of` bar against the realized next-bar direction once it's available)
- ⬜ Portfolio, Market Scanner, Risk Dashboard, Performance Analytics frontend pages still not built

## Phase 12 — Remaining frontend pages + prediction evaluation (this round)
- ✅ Prediction evaluation task (app/tasks/evaluation_tasks.py) — compares each prediction's `as_of`
  bar against the realized next-bar close in TimescaleDB, populates was_correct/actual_direction.
  Scheduled hourly via celery beat. This closes the gap flagged last round — /api/predictions/accuracy
  now reports a real number once evaluations have run, instead of permanently "not evaluated yet".
- ✅ /api/portfolio/performance — real Sharpe/Sortino/Calmar/drawdown/VaR/CVaR computed from actual
  equity-snapshot returns via the ai-engine; honestly reports insufficient-data rather than faking metrics
- ✅ /api/scanner/scan — real technical scan (RSI/ADX/trend) across a watchlist using live TimescaleDB
  bars run through the same feature pipeline as AI Predictions; transparent threshold rules, not a
  black-box score; symbols without enough backfilled history report signal="no_data"
- ✅ /api/risk/summary — real open-position exposure (net/gross volume, unrealized PnL per symbol)
  and margin utilization from the latest broker equity snapshot
- ✅ Frontend: Portfolio (multi-account equity chart), Performance Analytics (risk metric cards),
  Market Scanner (live scan table), Risk Dashboard (exposure + margin tables) — all wired to the
  endpoints above, all with honest empty/insufficient-data states instead of placeholder numbers

All originally-planned nav pages are now built and backed by real endpoints. 62 backend + 24 ai-engine
Python files pass a full syntax sweep; frontend TSX files brace/paren-balance checked (no tsc available
in this sandbox — run `npm run build` locally to fully verify).

## What's left for a genuinely production-hardened deploy
- Run everything against real Postgres/Redis/TimescaleDB locally (`docker compose up`) — this sandbox
  has no network, so nothing here has been integration-tested end-to-end, only unit-verified.
- Test coverage: broker adapters (mocked SDKs), auth endpoints (test DB), backtest engine, execution
  engine, smart_money detectors, the new portfolio/scanner/risk/prediction routers.
- Alembic migrations have never been run against a live DB in this environment — verify with
  `alembic upgrade head` before relying on the schema.
- TLS/HTTPS termination, production secrets management (this repo only has .env), and a real
  Kubernetes/production Docker Swarm deployment story are not yet written.

## Phase 13 — "Top tier" feature batch (this round)
Real, compiling, partially-tested additions:
- ✅ Paper trading adapter (app/brokers/paper_adapter.py) — full BrokerAdapter implementation
  filling simulated orders against real live quotes; new `paper` broker type, selectable in Settings,
  powers a genuine no-funded-account demo mode
- ✅ OCO orders (app/execution/oco.py) — application-level one-cancels-other (neither MT5 nor MetaApi
  natively support it), polling-based with an honestly-documented race-condition caveat
- ✅ stop_limit order type — added to BrokerOrderType + OrderRequest.stop_price + MT5 adapter mapping
- ✅ Circuit breaker (app/execution/circuit_breaker.py) — intraday drawdown + single-position runaway-loss
  auto-flatten, scheduled every 2 min via Celery; in-process trip state flagged as needing Redis for
  multi-worker deployments
- ✅ Correlation-aware position sizing (correlation_adjusted_size) + concentration limit in RiskGuard —
  11 new tests, all passing (22/22 total in the pure-stdlib suite now)
- ✅ Live quote WebSocket (/ws/quotes) + reconnecting frontend hook, wired into the trading terminal's
  live bid/ask display
- ✅ Ensemble forecaster — LightGBM + XGBoost probability blend (previously LightGBM-only; XGBoost was
  in requirements.txt but unused until now), per-model breakdown + blended feature importances surfaced
  through the API and the AI Predictions page
- ✅ Backtest HTML report generator (app/backtest/report.py) + /backtest/run endpoint + example SMA
  crossover strategy — real equity curve (inline SVG), trade log, risk metrics, Monte Carlo robustness
- ✅ Dark/light theme toggle — real CSS-variable-driven, not just a class name; persisted, wired into Tailwind tokens
- ✅ Terraform IaC (infra/terraform/) — VPC/subnets/security groups, RDS Postgres + RDS-with-timescaledb-extension
  + ElastiCache Redis, ECS Fargate + ECR, CodeDeploy blue/green with linear traffic shifting and
  CloudWatch-5xx-triggered auto-rollback, Secrets Manager (no plaintext secrets in any resource)
- ✅ Locust load test (infra/loadtest/) — real scenarios against actual auth/orders/risk/scanner/predictions
  endpoints, separate weight class for the expensive AI-prediction path
- ✅ CI deploy job — ECR push + CodeDeploy trigger gated to main + a required GitHub environment approval
  (the CodeDeploy revision JSON is flagged inline as illustrative — needs a real templating step for the
  task-def ARN substitution before it's runnable as-is, not claimed as finished automation)
- ✅ DB connection pooling (pool_size/max_overflow/pool_recycle) + read-replica engine pattern, wired into
  the actual read-heavy endpoints (portfolio, risk) via a new get_read_db dependency

94 backend + ai-engine Python files pass a full syntax sweep; Terraform files brace-balance checked
(no terraform CLI in this sandbox — run `terraform validate` locally); 22/22 executable tests pass.

## Explicitly NOT done — scope that was too large for this pass
- **RL position-sizing agent** — genuinely substantial (environment design, reward shaping, training
  loop, PyTorch/stable-baselines3 integration, evaluation). Not started. If wanted next, this alone is
  probably a multi-session undertaking, not an add-on to this batch.
- **Multi-strategy capital allocator** — needs a strategy registry + rolling-Sharpe-based reallocation
  logic + its own DB schema (strategies, allocations tables). Not started.
- **Copy trading across accounts** — needs a trade-mirroring service + per-account scaling rules. Not started.
- **News/sentiment model consumption as a feature** — the HF selector discovers and ranks sentiment models;
  nothing yet fetches news and feeds a sentiment score into build_feature_matrix. Not started.
- **KYC/AML stub** — not started; lower priority for a portfolio project unless going multi-tenant for real.
- **Actual HashiCorp Vault client code** — secrets.tf documents the AWS Secrets Manager pattern; a literal
  Vault SDK integration in app/core/config.py was not written (the substitution is straightforward but
  wasn't done).
- Nothing in this batch has been run against live infra — same caveat as every previous phase: no network
  in this sandbox, so integration testing (docker compose up, terraform apply, an actual load test run)
  is still on you.

## Phase 14 — RL position-sizing agent (this round)
The last explicitly-deferred item from the "top tier" list. Scoped deliberately narrow and stated
honestly: this agent does NOT choose trade direction — direction comes from a fixed EMA12/EMA26
trend rule. The RL agent's only job is *how much size* (0-100%, discretized into 5 bins) to allocate
to that direction each bar, trained via DQN to maximize risk-adjusted reward (P&L minus transaction
cost minus a drawdown penalty).

- ✅ app/rl/reward.py — pure-stdlib reward math (pnl/cost/drawdown-penalty), zero ML dependencies.
  **Actually executed in this sandbox** (not just syntax-checked): 18/18 manual verification checks
  passed against the real implementation, mirroring every case in tests/test_rl_reward.py.
- ✅ app/rl/replay_buffer.py — standard fixed-capacity experience replay (numpy-backed)
- ✅ app/rl/environment.py — PositionSizingEnv, gym-style reset()/step() over real historical bars,
  state = normalized technical/regime features + account state, 5-bin discrete action space
- ✅ app/rl/agent.py — real PyTorch DQN: 2-hidden-layer Q-network, separate target network, Huber loss,
  gradient clipping, epsilon-greedy with linear decay — standard Mnih et al. components, not a toy
- ✅ app/rl/train.py — training loop (episodes over random historical windows) + inference-time
  suggest_size() with a Q-value-gap-based confidence proxy (explicitly labeled as a heuristic, not a
  calibrated probability)
- ✅ ai-engine endpoints: POST /rl/train (slow, real training run), POST /rl/suggest-size (per-symbol
  cached agent, 12h staleness check)
- ✅ Backend: RLSizingSuggestion model + migration (audit trail, same pattern as Prediction), POST
  /api/rl/train, POST /api/rl/suggest-size, GET /api/rl/suggestions — pulls real TimescaleDB bars,
  proxies to ai-engine, persists every suggestion
- ✅ Frontend: RL Position Sizing card on the AI Predictions page — train/get-suggestion buttons,
  confidence + suggested size display

71 backend + 33 ai-engine files pass a full syntax sweep. 22/22 backend pure-stdlib tests still pass
(no regressions). The reward math (the one RL component that's dependency-free) is genuinely verified;
the environment/agent/training loop are syntax-verified only — no torch/numpy in this sandbox to
actually run a training episode. **This has never been trained end-to-end.** First real test is
running `POST /api/rl/train` against a live stack with real backfilled data.

Also explicitly still not done, unchanged from Phase 13: multi-strategy capital allocator, copy
trading, news/sentiment feature wiring, KYC/AML stub, literal Vault SDK integration.

## Phase 15 — The four remaining "top tier" items (this round)
Built for real, at the same standard as everything else — no stubs. See
docs/TESTING_CHECKLIST.md for the exact file-by-file testing plan before committing.

- ✅ **Vault secrets integration** — real hvac client wrapper (app/core/vault.py), wired into
  Settings via apply_vault_overrides(); no-op fallback to plain env vars keeps local dev working
  with zero Vault dependency.
- ✅ **News/sentiment feature** — real NewsAPI + Finnhub fetchers, FinBERT-based scoring with an
  honest lexicon-based fallback (6/6 checks actually run and passing), persisted SentimentSnapshot
  audit trail. Scoped explicitly as a real-time-only signal — NOT backfilled into the
  DirectionalForecaster's historical training, since there's no historical news archive to do that
  correctly with.
- ✅ **Multi-strategy capital allocator** — pure-stdlib rolling-Sharpe -> softmax -> bounded
  water-filling algorithm. **A real bug was caught and fixed during testing**: the first
  implementation's clip-then-renormalize step could push a bounded strategy's weight back above its
  own max bound; rewritten as proper iterative water-filling, 10/10 tests passing including the
  specific regression case. Daily Celery reallocation task + API. Honest gap: nothing yet writes
  StrategyTrade rows from live position closes, so every strategy currently looks "new" to the
  allocator until that wiring is added.
- ✅ **Copy trading** — real order-mirroring service, two scaling modes (fixed_ratio,
  equity_proportional), sizing math split into a dependency-free module and actually tested (6/6
  passing). Wired into the live order-placement flow in orders.py. **A real scoping bug was caught
  while wiring this in**: `broker_request` could be referenced before assignment if the broker
  connection failed before the request was built — fixed with an explicit `is not None` guard.

62 real executed checks across this session (sizing/risk_guard 22, allocator 10, copytrading 6,
RL reward 18, sentiment lexicon 6), two genuine bugs found and fixed by that testing. 90 backend +
35 ai-engine files pass a full syntax sweep.

This closes out every item from the original "top tier" list. Nothing has been run against live
infrastructure (Postgres/Redis/TimescaleDB/real brokers) — see docs/TESTING_CHECKLIST.md.
cd /workspaces/themarket/themarket-ai-quant-forex/apps/ai-engine && python3 - <<'PY'
from pathlib import Path
p = Path('app/indicators/technical.py')
text = p.read_text()
text = text.replace('''def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing (the standard RSI definition), equivalent to an EMA with
    # alpha = 1/period.
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
''', '''def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing (the standard RSI definition), equivalent to an EMA with
    # alpha = 1/period.
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_values = 100 - (100 / (1 + rs))

    rsi_values = rsi_values.where(~np.isnan(rsi_values), 100.0)
    return rsi_values.clip(0.0, 100.0)
''')
p.write_text(text)
PY
python3 - <<'PY'
from pathlib import Path
p = Path('app/risk/metrics.py')
text = p.read_text()
text = text.replace('''def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns - risk_free_rate / periods_per_year
    if excess.std(ddof=0) == 0:
        return 0.0
    return float(excess.mean() / excess.std(ddof=0) * annualization_factor(periods_per_year))
''', '''def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns - risk_free_rate / periods_per_year
    std = excess.std(ddof=0)
    if np.isnan(std) or std == 0:
        return 0.0
    return float(excess.mean() / std * annualization_factor(periods_per_year))
''')
text = text.replace('''def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    downside_std = downside.std(ddof=0)
    if downside_std == 0 or np.isnan(downside_std):
        return 0.0
    return float(excess.mean() / downside_std * annualization_factor(periods_per_year))
''', '''def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    downside_std = downside.std(ddof=0)
    if np.isnan(downside_std) or downside_std == 0:
        return 0.0
    return float(excess.mean() / downside_std * annualization_factor(periods_per_year))
''')
p.write_text(text)
PY