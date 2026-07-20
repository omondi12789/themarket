from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.accounts import router as accounts_router
from app.api.auth import router as auth_router
from app.api.copytrading import router as copytrading_router
from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.api.portfolio import router as portfolio_router
from app.api.predictions import router as predictions_router
from app.api.risk import router as risk_router
from app.api.rl import router as rl_router
from app.api.scanner import router as scanner_router
from app.api.sentiment import router as sentiment_router
from app.api.strategies import router as strategies_router
from app.api.websocket import router as websocket_router
from app.core.config import get_settings
from app.middleware.metrics import MetricsMiddleware
from app.middleware.metrics import router as metrics_router
from app.middleware.security import RateLimitMiddleware, SecurityHeadersMiddleware

settings = get_settings()

app = FastAPI(
    title="THEMARKET AI Quant Forex — Backend",
    version="0.1.0",
    docs_url="/docs" if settings.env != "production" else None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_window=100, window_seconds=60)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(accounts_router, prefix="/api")
app.include_router(copytrading_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(portfolio_router, prefix="/api")
app.include_router(predictions_router, prefix="/api")
app.include_router(scanner_router, prefix="/api")
app.include_router(risk_router, prefix="/api")
app.include_router(rl_router, prefix="/api")
app.include_router(sentiment_router, prefix="/api")
app.include_router(strategies_router, prefix="/api")
app.include_router(websocket_router)


@app.get("/")
async def root() -> dict:
    return {"service": "themarket-ai-quant-forex-backend", "status": "running"}
