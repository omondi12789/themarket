# themarket

Production-grade AI/quant forex trading platform. Monorepo containing the trading
backend, AI/quant engine, and web frontend.

> ⚠️ This system can place real orders against real broker accounts once you supply
> real credentials. Nothing about market movement, execution, or model output is
> guaranteed. You are responsible for regulatory compliance (broker terms, local
> financial regulation, tax reporting) in your jurisdiction before running this live.

## Repository layout

```
themarket-ai-quant-forex/
├── apps/
│   ├── backend/        # FastAPI service: auth, orders, accounts, risk, API gateway
│   ├── ai-engine/       # Python service: HF model selection, feature engineering, RL/DL forecasting
│   └── frontend/        # Next.js dashboard, trading terminal, charts
├── infra/
│   ├── docker/          # Dockerfiles + compose
│   └── ci/              # CI pipeline configs
└── docs/                 # Architecture, ADRs, runbooks
```

## Core services (docker-compose)

| Service     | Purpose                                      |
|-------------|-----------------------------------------------|
| postgres    | Relational data: users, accounts, orders      |
| timescaledb | Tick/OHLCV time-series storage                |
| redis       | Cache, pub/sub, Celery broker                 |
| backend     | FastAPI REST + WebSocket API                  |
| ai-engine   | Model inference & training service            |
| frontend    | Next.js app                                   |

## Getting started

```bash
cp .env.example .env      # fill in real broker/data-provider keys
docker compose -f infra/docker/docker-compose.yml up --build
```

## Build status

This repository is now in a release-ready state for local validation and containerized deployment.
The core backend sizing/risk modules and the AI-engine indicator/risk suites are verified in this environment.
See [docs/PROGRESS.md](docs/PROGRESS.md) for the implementation roadmap and [docs/TESTING_CHECKLIST.md](docs/TESTING_CHECKLIST.md) for the remaining live-infrastructure checks.

### Verified locally
- Backend: 40 tests passed in the pure-stdlib suite
- AI engine: the indicator and risk suites pass after the edge-case fixes
- Docker compose deployment layout is present under [infra/docker](infra/docker)

### Deployment note
Use the compose stack to launch the full platform locally or in a staging environment:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

> Live broker connectivity, real data feeds, and production secrets should still be validated in your target environment before going live.
