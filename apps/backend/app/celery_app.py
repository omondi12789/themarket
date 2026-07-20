"""
Celery app: background worker for scheduled jobs (market data backfill, equity
snapshots, future model retraining). Broker/backend both point at Redis — simplest
viable setup for this stage; swap the backend to Postgres/RabbitMQ later if job
result persistence needs outlive Redis's.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "themarket_ai_quant_forex",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.market_data_tasks",
        "app.tasks.portfolio_tasks",
        "app.tasks.evaluation_tasks",
        "app.tasks.circuit_breaker_tasks",
        "app.tasks.allocator_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=15 * 60,
)

celery_app.conf.beat_schedule = {
    "backfill-watchlist-hourly": {
        "task": "app.tasks.market_data_tasks.backfill_watchlist_task",
        "schedule": crontab(minute=5),  # 5 minutes past every hour
    },
    "snapshot-account-equity-every-15-min": {
        "task": "app.tasks.portfolio_tasks.snapshot_all_account_equity_task",
        "schedule": crontab(minute="*/15"),
    },
    "evaluate-pending-predictions-hourly": {
        "task": "app.tasks.evaluation_tasks.evaluate_pending_predictions_task",
        "schedule": crontab(minute=20),
    },
    "circuit-breaker-check-every-2-min": {
        "task": "app.tasks.circuit_breaker_tasks.check_circuit_breakers_task",
        "schedule": crontab(minute="*/2"),
    },
    "reallocate-capital-daily": {
        "task": "app.tasks.allocator_tasks.reallocate_capital_task",
        "schedule": crontab(hour=0, minute=30),
    },
}
