# Load Testing

Real Locust scenarios against the actual backend API (not synthetic/mocked endpoints).

## Run locally

```bash
pip install -r requirements.txt --break-system-packages
locust -f locustfile.py --host http://localhost:8000
```

Open http://localhost:8089, set concurrent users and spawn rate, start the test.

## Headless (CI-friendly) run producing a report

```bash
locust -f locustfile.py --host http://localhost:8000 \
  --users 200 --spawn-rate 10 --run-time 5m \
  --headless --html report.html --csv results
```

## What's modeled

- `TraderUser` — read-heavy: accounts, orders, risk summary, market scan, equity history
  (weighted to match realistic usage: dashboard/positions checked far more often than
  orders are placed)
- `HeavyPredictionUser` — the expensive path (AI prediction generation, which
  trains/loads a gradient-boosted model), reported separately in Locust's UI so its
  latency distribution isn't averaged together with the cheap read endpoints

## Interpreting results

Watch p95/p99 latency on `/api/predictions/generate` specifically — it's the one
endpoint doing real ML training/inference per request (see the per-symbol model
cache in `apps/ai-engine/app/main.py`, which is exactly the optimization this load
test would tell you whether you still need to tune).
