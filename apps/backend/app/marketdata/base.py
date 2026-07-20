"""
Market data provider abstraction.

Same pattern as app/brokers/base.py: one interface, several real adapters
(Polygon, TwelveData, Finnhub), so the ingestion job and the rest of the platform
don't care which provider is backing a given symbol/timeframe.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Timeframe(str, Enum):
    m1 = "1m"
    m5 = "5m"
    m15 = "15m"
    h1 = "1h"
    h4 = "4h"
    d1 = "1d"


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp: datetime


@dataclass(frozen=True)
class Tick:
    symbol: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime


class MarketDataError(Exception):
    pass


class MarketDataProvider(abc.ABC):
    provider_name: str

    @abc.abstractmethod
    async def get_historical_bars(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[Bar]:
        ...

    @abc.abstractmethod
    async def get_latest_quote(self, symbol: str) -> Tick:
        ...
