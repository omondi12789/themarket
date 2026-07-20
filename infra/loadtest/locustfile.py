"""
Load test against the real backend API surface. Run with:
    locust -f locustfile.py --host http://localhost:8000

Scenarios modeled on actual traffic shape: most users check the dashboard/positions
repeatedly (read-heavy), a smaller fraction place orders (write, and the one path
that touches a broker adapter + DB transaction + audit log), and a slice hit the
AI predictions endpoint (the most compute-heavy call — trains/loads a model).
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]


class TraderUser(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        """Register + log in once per simulated user, mirroring real session behavior."""
        email = f"loadtest_{random.randint(1, 10_000_000)}@example.com"
        password = "LoadTest123!SecurePass"

        self.client.post("/api/auth/register", json={"email": email, "password": password})
        resp = self.client.post("/api/auth/login", json={"email": email, "password": password})
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}

    @task(10)
    def view_accounts(self):
        if self.headers:
            self.client.get("/api/accounts", headers=self.headers, name="/api/accounts")

    @task(8)
    def view_orders(self):
        if self.headers:
            self.client.get("/api/orders", headers=self.headers, name="/api/orders")

    @task(6)
    def view_risk_summary(self):
        if self.headers:
            self.client.get("/api/risk/summary", headers=self.headers, name="/api/risk/summary")

    @task(4)
    def run_market_scan(self):
        if self.headers:
            self.client.get("/api/scanner/scan", headers=self.headers, name="/api/scanner/scan")

    @task(3)
    def view_equity_history(self):
        if self.headers:
            self.client.get(
                "/api/portfolio/equity-history?days=7", headers=self.headers, name="/api/portfolio/equity-history"
            )

    @task(1)
    def health_check(self):
        self.client.get("/api/health", name="/api/health")


class HeavyPredictionUser(HttpUser):
    """
    A smaller weight class simulating the expensive path — AI prediction generation
    (trains/loads a gradient-boosted model). Separate class so Locust's UI reports
    this endpoint's latency distribution independently from the cheap read paths
    above, since averaging them together would hide how much slower this path is.
    """

    wait_time = between(5, 15)
    weight = 1  # spawn far fewer of these than TraderUser (weight defaults to 1 there but many more tasks)

    def on_start(self):
        email = f"loadtest_pred_{random.randint(1, 10_000_000)}@example.com"
        password = "LoadTest123!SecurePass"
        self.client.post("/api/auth/register", json={"email": email, "password": password})
        resp = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.headers = {"Authorization": f"Bearer {resp.json()['access_token']}"} if resp.status_code == 200 else {}

    @task
    def generate_prediction(self):
        if self.headers:
            symbol = random.choice(SYMBOLS)
            self.client.post(
                "/api/predictions/generate",
                json={"symbol": symbol, "timeframe": "1h"},
                headers=self.headers,
                name="/api/predictions/generate",
            )
