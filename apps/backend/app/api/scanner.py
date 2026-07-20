import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.marketdata.models import OHLCVBar
from app.marketdata.timescale_session import TimescaleSessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scanner", tags=["scanner"])

DEFAULT_WATCHLIST = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]


class ScanResult(BaseModel):
    symbol: str
    signal: str  # "overbought" | "oversold" | "trending_up" | "trending_down" | "neutral" | "no_data"
    rsi_14: float | None = None
    adx: float | None = None
    price_vs_sma20_pct: float | None = None
    bb_position: float | None = None
    note: str | None = None


def _classify(features: dict) -> str:
    rsi = features.get("rsi_14")
    adx = features.get("adx")
    price_vs_sma20 = features.get("price_vs_sma20")

    if rsi is not None and rsi >= 70:
        return "overbought"
    if rsi is not None and rsi <= 30:
        return "oversold"
    if adx is not None and adx >= 25 and price_vs_sma20 is not None:
        return "trending_up" if price_vs_sma20 > 0 else "trending_down"
    return "neutral"


@router.get("/scan", response_model=list[ScanResult])
async def scan_watchlist(
    symbols: str | None = Query(default=None, description="comma-separated, defaults to the standard majors"),
    timeframe: str = Query(default="1h"),
    user: User = Depends(get_current_user),
) -> list[ScanResult]:
    """
    Runs the real feature pipeline (same one AI Predictions and the quant engine use)
    against each symbol's latest bars and classifies the result with simple,
    transparent rules (RSI thresholds, ADX trend strength) — not a black-box "buy/sell"
    call. Symbols without enough backfilled history return signal="no_data" rather
    than being silently omitted or given a fabricated neutral reading.
    """
    watchlist = [s.strip().upper() for s in symbols.split(",")] if symbols else DEFAULT_WATCHLIST
    settings = get_settings()
    results: list[ScanResult] = []

    async with TimescaleSessionLocal() as ts_session, httpx.AsyncClient(timeout=20.0) as client:
        for symbol in watchlist:
            bar_result = await ts_session.execute(
                select(OHLCVBar)
                .where(OHLCVBar.symbol == symbol, OHLCVBar.timeframe == timeframe)
                .order_by(OHLCVBar.timestamp.desc())
                .limit(120)
            )
            bars = list(bar_result.scalars().all())

            if len(bars) < 60:
                results.append(
                    ScanResult(
                        symbol=symbol,
                        signal="no_data",
                        note=f"only {len(bars)}/60 bars backfilled for {symbol}/{timeframe}",
                    )
                )
                continue

            bars.reverse()
            bar_payload = [
                {
                    "timestamp": b.timestamp.isoformat(),
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume),
                }
                for b in bars
            ]

            try:
                resp = await client.post(f"{settings.ai_engine_url}/features/build", json={"bars": bar_payload})
                resp.raise_for_status()
                feature_payload = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("scanner: ai-engine call failed for %s: %s", symbol, exc)
                results.append(ScanResult(symbol=symbol, signal="no_data", note=f"ai-engine error: {exc}"))
                continue

            features = feature_payload.get("latest_features", {})
            results.append(
                ScanResult(
                    symbol=symbol,
                    signal=_classify(features),
                    rsi_14=features.get("rsi_14"),
                    adx=features.get("adx"),
                    price_vs_sma20_pct=(
                        features["price_vs_sma20"] * 100 if features.get("price_vs_sma20") is not None else None
                    ),
                    bb_position=features.get("bb_position"),
                )
            )

    return results
