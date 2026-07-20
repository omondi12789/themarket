from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from app.config import get_settings
from app.backtest.example_strategies import sma_crossover_strategy
from app.backtest.replay import Backtester
from app.backtest.report import generate_html_report
from app.features.pipeline import build_feature_matrix
from app.models.forecaster import DirectionalForecaster
from app.models.hf_selector import select_best_model
from app.quant.mathematical import strategy_bootstrap_robustness
from app.risk.metrics import summarize_performance

settings = get_settings()

app = FastAPI(title="THEMARKET AI Quant Forex — AI Engine", version="0.1.0")


@app.get("/")
async def root() -> dict:
    return {"service": "themarket-ai-quant-forex-ai-engine", "status": "running"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.env}


class Bar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class FeatureRequest(BaseModel):
    bars: list[Bar]


@app.post("/features/build")
async def build_features(request: FeatureRequest) -> dict:
    if len(request.bars) < 60:
        raise HTTPException(
            status_code=400,
            detail="Need at least 60 bars for stable indicator/regime warmup periods.",
        )

    df = pd.DataFrame([b.model_dump() for b in request.bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    matrix = build_feature_matrix(df)
    latest = matrix.iloc[-1].to_dict() if not matrix.empty else {}

    return {
        "rows_in": len(df),
        "rows_out": len(matrix),
        "columns": list(matrix.columns),
        "latest_features": {k: (None if pd.isna(v) else float(v)) for k, v in latest.items()},
    }


class ReturnsRequest(BaseModel):
    returns: list[float]
    periods_per_year: int = 252
    risk_free_rate: float = 0.0


@app.post("/risk/summary")
async def risk_summary(request: ReturnsRequest) -> dict:
    if len(request.returns) < 5:
        raise HTTPException(status_code=400, detail="Need at least 5 return observations.")
    series = pd.Series(request.returns)
    return summarize_performance(series, request.periods_per_year, request.risk_free_rate)


class RobustnessRequest(BaseModel):
    trade_returns: list[float]
    n_resamples: int = 5000


@app.post("/backtest/robustness")
async def backtest_robustness(request: RobustnessRequest) -> dict:
    """
    Monte Carlo robustness test (bootstrap resampling) on a completed backtest's
    per-trade returns — see PROJECT OUTPUT item 6 (backtesting engine)'s Monte Carlo
    robustness testing requirement.
    """
    if len(request.trade_returns) < 10:
        raise HTTPException(status_code=400, detail="Need at least 10 trade returns for a meaningful bootstrap.")
    series = pd.Series(request.trade_returns)
    return strategy_bootstrap_robustness(series, n_resamples=request.n_resamples)


@app.post("/models/select-best")
async def select_best(benchmark_top_n: int = 5) -> dict:
    """
    Runs the full HF discovery -> score -> benchmark -> re-score pipeline. This is a
    slow, network- and compute-heavy endpoint (downloads/loads real models) — call it
    from an admin/ops action or a scheduled job, not per-request inference.
    """
    try:
        winner, ranked = select_best_model(hf_token=settings.huggingface_token, benchmark_top_n=benchmark_top_n)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"model selection failed: {exc}") from exc

    return {
        "selected_model": winner.model_id,
        "composite_score": winner.composite_score,
        "score_breakdown": winner.scores,
        "measured_latency_ms": winner.measured_latency_ms,
        "license": winner.license,
        "top_10_ranking": [
            {
                "model_id": c.model_id,
                "composite_score": c.composite_score,
                "pipeline_tag": c.pipeline_tag,
                "license": c.license,
            }
            for c in ranked[:10]
        ],
    }


# --- Directional forecasting: per-symbol trained-model cache -----------------------
# Retraining a gradient-boosted model on every prediction request is wasteful (the
# model doesn't meaningfully change bar-to-bar); cache the fitted model per symbol
# and retrain when it goes stale. In-process dict is fine for a single ai-engine
# instance — move to Redis-backed if this service is ever horizontally scaled.
_MODEL_CACHE: dict[str, tuple[DirectionalForecaster, datetime, dict]] = {}
_MODEL_STALE_AFTER = timedelta(hours=6)


class PredictionRequest(BaseModel):
    symbol: str
    bars: list[Bar]
    force_retrain: bool = False


@app.post("/predictions/generate")
async def generate_prediction(request: PredictionRequest) -> dict:
    if len(request.bars) < 200:
        raise HTTPException(
            status_code=400,
            detail="Need at least 200 bars to train a meaningfully validated directional model.",
        )

    df = pd.DataFrame([b.model_dump() for b in request.bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    cached = _MODEL_CACHE.get(request.symbol)
    now = datetime.now(timezone.utc)
    needs_training = (
        request.force_retrain
        or cached is None
        or (now - cached[1]) > _MODEL_STALE_AFTER
    )

    if needs_training:
        forecaster = DirectionalForecaster()
        try:
            report = forecaster.train(df)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        training_report = {
            "n_train_samples": report.n_train_samples,
            "n_features": report.n_features,
            "cv_accuracy_mean": report.cv_accuracy_mean,
            "cv_accuracy_std": report.cv_accuracy_std,
            "top_features": report.feature_importances,
        }
        _MODEL_CACHE[request.symbol] = (forecaster, now, training_report)
    else:
        forecaster, _, training_report = cached

    prediction = forecaster.predict_latest(df)

    return {
        "symbol": request.symbol,
        "prediction": {
            "direction": prediction["direction"],
            "probability_up": prediction["probability_up"],
            "confidence": prediction["confidence"],
            "as_of": prediction["as_of"],
            "model_breakdown": prediction["model_breakdown"],
        },
        "model_info": {
            "model_type": "LightGBM + XGBoost ensemble (probability-averaged)",
            "trained_at": _MODEL_CACHE[request.symbol][1].isoformat(),
            "retrained_this_request": needs_training,
            **training_report,
        },
        "disclaimer": (
            "Cross-validated accuracy above is on historical data with proper "
            "time-series splitting (no look-ahead), but is not a guarantee of future "
            "performance. Treat this as one weighted input alongside quant signals "
            "and risk checks, not a standalone trade trigger."
        ),
    }


class BacktestRunRequest(BaseModel):
    symbol: str
    bars: list[Bar]
    fast_period: int = 10
    slow_period: int = 30
    starting_capital: float = 10000.0
    spread_pips: float = 1.0
    run_robustness: bool = True


@app.post("/backtest/run", response_class=Response)
async def run_backtest(request: BacktestRunRequest) -> Response:
    """
    Runs the SMA-crossover example strategy through the real replay backtester and
    returns a self-contained HTML report (equity curve, trade stats, risk metrics,
    Monte Carlo robustness). Swap `sma_crossover_strategy` for any other
    Backtester-compatible strategy callable to report on a different strategy.
    """
    if len(request.bars) < request.slow_period + 20:
        raise HTTPException(
            status_code=400,
            detail=f"need at least {request.slow_period + 20} bars for a meaningful backtest",
        )

    df = pd.DataFrame([b.model_dump() for b in request.bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    backtester = Backtester(starting_capital=request.starting_capital, spread_pips=request.spread_pips)
    strategy = sma_crossover_strategy(request.fast_period, request.slow_period)
    result = backtester.run(df, strategy, warmup_bars=request.slow_period + 5)

    robustness = None
    if request.run_robustness and len(result.trades) >= 10:
        robustness = strategy_bootstrap_robustness(result.trade_returns, n_resamples=2000)

    html = generate_html_report(
        result,
        strategy_name=f"SMA Crossover ({request.fast_period}/{request.slow_period})",
        symbol=request.symbol,
        robustness=robustness,
    )
    return Response(content=html, media_type="text/html")


# --- RL position sizing: per-symbol trained-agent cache ---------------------------
from app.rl.agent import DQNAgent
from app.rl.environment import N_ACTIONS, PositionSizingEnv
from app.rl.train import TrainingCurve, suggest_size, train_position_sizing_agent

_RL_AGENT_CACHE: dict[str, tuple[DQNAgent, PositionSizingEnv, datetime, TrainingCurve]] = {}
_RL_STALE_AFTER = timedelta(hours=12)


class RLTrainRequest(BaseModel):
    symbol: str
    bars: list[Bar]
    n_episodes: int = 150
    episode_length: int = 200
    force_retrain: bool = False


@app.post("/rl/train")
async def rl_train(request: RLTrainRequest) -> dict:
    """
    Trains the DQN position-sizing agent on real historical bars. This is a genuinely
    slow endpoint (150 episodes x up to 200 steps each, with a gradient step per
    environment step) — call it from an admin action or scheduled retraining job,
    not inline with a trade decision. Cached per symbol; /rl/suggest-size reuses the
    trained agent until it goes stale or force_retrain is requested here again.
    """
    if len(request.bars) < request.episode_length + 100:
        raise HTTPException(
            status_code=400,
            detail=(
                f"need at least {request.episode_length + 100} bars "
                f"(episode_length={request.episode_length} + feature warmup + buffer)"
            ),
        )

    df = pd.DataFrame([b.model_dump() for b in request.bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    try:
        env = PositionSizingEnv(df, episode_length=request.episode_length)
        agent, curve = train_position_sizing_agent(
            df, n_episodes=request.n_episodes, episode_length=request.episode_length
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    _RL_AGENT_CACHE[request.symbol] = (agent, env, now, curve)

    return {
        "symbol": request.symbol,
        "trained_at": now.isoformat(),
        "training_summary": curve.summary(),
        "disclaimer": (
            "Training reward reflects this environment's specific reward shaping "
            "(risk-adjusted P&L minus transaction cost and drawdown penalty) over "
            "this historical window, using a fixed EMA-crossover direction signal. "
            "It is not a backtest of a complete trading strategy and does not "
            "guarantee any future performance."
        ),
    }


@app.post("/rl/suggest-size")
async def rl_suggest_size(request: PredictionRequest) -> dict:
    """Reuses PredictionRequest's schema (symbol + bars) since the shape is identical."""
    cached = _RL_AGENT_CACHE.get(request.symbol)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=f"no trained RL agent for {request.symbol} — call /rl/train first",
        )

    agent, env, trained_at, curve = cached
    if datetime.now(timezone.utc) - trained_at > _RL_STALE_AFTER:
        raise HTTPException(
            status_code=409,
            detail=f"RL agent for {request.symbol} is stale (trained {trained_at.isoformat()}) — retrain via /rl/train",
        )

    df = pd.DataFrame([b.model_dump() for b in request.bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    try:
        eval_env = PositionSizingEnv(df, episode_length=min(50, len(df) - 65))
        obs = eval_env.reset(start_idx=eval_env.n_usable_bars - 2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = suggest_size(agent, eval_env, obs)

    return {
        "symbol": request.symbol,
        "agent_trained_at": trained_at.isoformat(),
        "agent_training_summary": curve.summary(),
        **result,
        "disclaimer": (
            "This is a position-SIZE suggestion only (0-1 fraction of max allocation), "
            "not a direction call — direction comes from a fixed EMA-crossover rule in "
            "this environment. Treat as one input to the sizing decision, not a standalone signal."
        ),
    }


# --- News sentiment scoring ---------------------------------------------------------
from app.sentiment.finbert import aggregate_sentiment, score_headlines


class SentimentRequest(BaseModel):
    headlines: list[str]


@app.post("/sentiment/score")
async def sentiment_score(request: SentimentRequest) -> dict:
    """
    Scores a batch of real headlines (fetched by the backend from NewsAPI/Finnhub —
    see apps/backend/app/news/client.py) with FinBERT, falling back to a small
    lexicon scorer if the model can't be loaded. This is a real-time signal only:
    there is no historical news archive backfilled here, so this does NOT feed the
    DirectionalForecaster's historical training (that would need years of
    point-in-time news data this project doesn't have access to) — it's exposed as
    its own live signal instead, honestly scoped rather than silently faked into
    the trained model's feature set.
    """
    if not request.headlines:
        raise HTTPException(status_code=400, detail="headlines list is empty")
    if len(request.headlines) > 100:
        raise HTTPException(status_code=400, detail="max 100 headlines per request")

    results = score_headlines(request.headlines)
    aggregate = aggregate_sentiment(results)

    return {
        "aggregate": aggregate,
        "headlines": [
            {"text": text, "label": r.label, "score": r.score, "method": r.method}
            for text, r in zip(request.headlines, results)
        ],
    }
