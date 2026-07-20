# Testing Checklist — Phase 15 (Vault, News/Sentiment, Multi-Strategy Allocator, Copy Trading)

Everything below is real code, syntax-verified (full `ast.parse` sweep: 90 backend + 35
ai-engine files, zero errors) and — where the code has zero external dependencies —
actually executed and passing in this sandbox. Nothing has been run against a live
Postgres/Redis/broker stack. Test in roughly this order; each section notes what's
already verified vs. what you still need to check.

## 1. Vault secrets integration
**Already verified:** compiles clean; `get_secret()` gracefully falls back to env vars
when Vault isn't configured (this is the code path local dev will actually exercise).
**You need to test:**
- `apps/backend/app/core/vault.py` — point `VAULT_ADDR`/`VAULT_TOKEN` at a real Vault
  dev server (`vault server -dev`), write a test secret, confirm `get_secret()` reads it.
- `apps/backend/app/core/config.py` (`apply_vault_overrides`) — confirm it correctly
  overrides `database_url`/`redis_url`/`jwt_secret`/`jwt_refresh_secret`/`fernet_key`
  only when `VAULT_SECRET_PATH_PREFIX` is set, and is a true no-op otherwise.
- `requirements.txt` — confirm `hvac==2.3.0` actually installs and pins to a version
  compatible with your Vault server.

## 2. News / sentiment feature
**Already verified:** `apps/ai-engine/app/sentiment/finbert.py`'s lexicon fallback —
6/6 real checks executed and passing (positive/negative/neutral classification,
aggregation, empty-input handling).
**You need to test:**
- `apps/ai-engine/app/sentiment/finbert.py` — the FinBERT path itself (`_score_with_finbert`)
  needs network access to download `ProsusAI/finbert` weights on first run; confirm it
  actually loads and produces sane labels on a few real financial headlines, and that
  the fallback genuinely triggers (kill network mid-request or mock the import) rather
  than silently erroring.
- `apps/backend/app/news/client.py` — both `NewsAPIClient` and `FinnhubNewsClient`
  against real API keys; confirm response parsing matches the actual current API
  response shape (these providers occasionally change field names — verify against
  live responses, not just this code's assumptions).
- `apps/backend/app/api/sentiment.py` (`POST /api/sentiment/refresh`) — full round trip:
  backend fetches news -> calls ai-engine -> persists `SentimentSnapshot`. Check the
  failover from NewsAPI to Finnhub actually engages when `NEWSAPI_KEY` is unset/invalid.
- Migration `0007_add_sentiment_snapshots.py` — run `alembic upgrade head` and confirm
  the table is created correctly.

## 3. Multi-strategy capital allocator
**Already verified — and this is where testing caught a real bug:** the initial
clip-then-renormalize implementation could push a bounded strategy's weight back
above its own max bound after renormalizing. Rewritten as proper iterative
water-filling; 10/10 tests now pass, including the specific case that failed before
(`test_compute_allocations_respects_max_bound`). This is exactly the kind of bug that
would NOT have surfaced from a syntax check alone — worth re-running these tests
yourself after any further changes to `allocator.py`.
**You need to test:**
- `apps/backend/app/execution/allocator.py` — run `tests/test_allocator.py` under real
  pytest (`pip install pytest && pytest tests/test_allocator.py -v`) to confirm my
  manual verification matches pytest's actual result.
- `apps/backend/app/tasks/allocator_tasks.py` — needs a live DB with `Strategy` and
  `StrategyTrade` rows; confirm `reallocate_capital_task` correctly updates
  `Strategy.capital_allocation_pct` and that the daily Celery beat schedule fires.
- `apps/backend/app/api/strategies.py` — `POST /api/strategies`, `GET /api/strategies`,
  `POST /api/strategies/reallocate` against a live backend.
- **Known gap, not a bug to fix so much as unfinished wiring:** nothing currently
  writes `StrategyTrade` rows from live position closes (see that model's docstring).
  Until you wire a position-close handler to insert them, every strategy will look
  "new" to the allocator and get the flat default allocation. This is the one piece
  of this feature that's more "unimplemented" than "untested" — flagging clearly so
  it's not mistaken for a bug in the allocator itself.
- Migration `0008_add_strategies.py`.

## 4. Copy trading
**Already verified:** `apps/backend/app/execution/copytrading_sizing.py` — 6/6 real
checks executed and passing (fixed_ratio, equity_proportional, bound enforcement,
below-minimum skip, and both `ValueError` cases for missing/zero equity).
**You need to test:**
- `apps/backend/app/execution/copytrading.py` (`mirror_order`) — the I/O orchestration
  around the verified-correct sizing math: needs a live DB with `CopyTradingLink` rows
  and at least two connected broker accounts (paper adapter is the easy way to test
  this without funded accounts). Confirm one follower's broker failure doesn't affect
  another follower or the source order.
- `apps/backend/app/api/orders.py` — confirm the `broker_request is not None` guard
  I added actually prevents a `NameError` when `get_adapter_for_account` raises before
  `broker_request` is constructed (this was a real scoping bug I caught and fixed while
  wiring this in — worth a specific regression test for "source broker connection fails
  entirely" to confirm order placement still returns a clean rejection rather than a
  500 error).
- `apps/backend/app/api/copytrading.py` — `POST /api/copytrading/links`,
  `GET /api/copytrading/links`, `DELETE /api/copytrading/links/{id}`, including the
  ownership checks (both source and follower must belong to the requesting user).
- Migration `0009_add_copy_trading.py`.

## Files touched but not new (regression risk — re-run existing suites)
- `apps/backend/app/core/config.py` — gained new fields; confirm existing settings-dependent
  code (auth, brokers, market data) still initializes correctly.
- `apps/backend/app/api/orders.py` — the order-placement flow gained the copy-trading
  hook; re-run `tests/test_sizing.py` and `tests/test_risk_guard.py` (still 22/22 as of
  this commit) plus manually exercise a normal order placement to confirm no regression.
- `apps/backend/alembic/env.py` — now imports 9 model modules; confirm `alembic upgrade
  head` runs cleanly through all 9 migrations in sequence on a fresh database.

## Suggested test order
1. `alembic upgrade head` on a throwaway DB — catches any migration ordering/FK issues first.
2. `pytest apps/backend/tests/ -v` and `pytest apps/ai-engine/tests/ -v` — confirms my
   manual verification against real pytest.
3. `docker compose up` — first real integration test of the whole stack together.
4. Connect two paper-trading accounts, create a copy-trading link, place one order,
   confirm the mirror executes.
5. Register a strategy, manually trigger `/api/strategies/reallocate`, confirm it
   returns default allocations (expected, given the StrategyTrade gap above) rather
   than erroring.
