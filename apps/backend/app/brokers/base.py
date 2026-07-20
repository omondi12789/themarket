"""
Broker abstraction layer.

Every concrete broker connection (official MetaTrader5 python package, MetaApi cloud,
future MT4 bridge) implements this interface. Nothing else in the codebase — order
router, risk engine, scalping engine, backtester-vs-live comparisons — talks to a
broker SDK directly. This is what makes "swap MT5 for MetaApi" a config change
instead of a rewrite.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class BrokerOrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class BrokerOrderType(str, Enum):
    market = "market"
    limit = "limit"
    stop = "stop"
    stop_limit = "stop_limit"


@dataclass(frozen=True)
class AccountSnapshot:
    login: str
    broker_server: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    currency: str
    leverage: int
    is_live: bool


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: BrokerOrderSide
    order_type: BrokerOrderType
    volume: Decimal
    price: Decimal | None = None  # limit price (for limit/stop_limit orders)
    stop_price: Decimal | None = None  # trigger price (for stop/stop_limit orders)
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    client_order_id: str | None = None
    comment: str = ""


@dataclass(frozen=True)
class OrderResult:
    broker_order_id: str
    status: str
    filled_price: Decimal | None
    filled_volume: Decimal
    submitted_at: datetime
    raw: dict


@dataclass(frozen=True)
class BrokerPosition:
    broker_position_id: str
    symbol: str
    side: BrokerOrderSide
    volume: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None


class BrokerConnectionError(Exception):
    """Raised when a broker adapter cannot establish or maintain a session."""


class BrokerOrderError(Exception):
    """Raised when a broker rejects or fails to execute an order."""


class BrokerAdapter(abc.ABC):
    """Common interface for every broker integration."""

    broker_type: str

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish a session with the broker. Raises BrokerConnectionError on failure."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        ...

    @abc.abstractmethod
    async def get_account_snapshot(self) -> AccountSnapshot:
        ...

    @abc.abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        ...

    @abc.abstractmethod
    async def stream_quotes(self, symbols: list[str]):
        """Async generator yielding Quote objects as they arrive."""

    @abc.abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Raises BrokerOrderError if the broker rejects the order."""

    @abc.abstractmethod
    async def cancel_order(self, broker_order_id: str) -> None:
        ...

    @abc.abstractmethod
    async def get_open_positions(self) -> list[BrokerPosition]:
        ...

    @abc.abstractmethod
    async def close_position(self, broker_position_id: str, volume: Decimal | None = None) -> OrderResult:
        """volume=None closes the full position; a Decimal partially closes it."""
