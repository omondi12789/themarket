"""
OCO (one-cancels-other) order management.

Neither the official MT5 package nor MetaApi expose a native OCO primitive — this is
standard; most retail platforms implement OCO at the application layer by watching
both legs and cancelling the sibling when one fills. This module does exactly that:
it doesn't place two "linked" broker orders, it places two independent pending orders
and polls their status, cancelling the other the moment one fills or triggers.

Reality check: polling-based OCO has an inherent race window (both legs could fill in
the same poll interval during a fast market gap) — acceptable for typical retail FX
volatility at a 1-2s poll interval, but this is not exchange-grade atomic OCO.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from app.brokers.base import BrokerAdapter, BrokerOrderError, OrderRequest, OrderResult

logger = logging.getLogger(__name__)


class OCOStatus(str, Enum):
    pending = "pending"
    leg_a_filled = "leg_a_filled"
    leg_b_filled = "leg_b_filled"
    cancelled = "cancelled"
    error = "error"


@dataclass
class OCOGroup:
    group_id: str
    leg_a_request: OrderRequest
    leg_b_request: OrderRequest
    leg_a_broker_order_id: str | None = None
    leg_b_broker_order_id: str | None = None
    status: OCOStatus = OCOStatus.pending
    fill_result: OrderResult | None = None


class OCOManager:
    def __init__(self, broker: BrokerAdapter, poll_interval_seconds: float = 1.5):
        self.broker = broker
        self.poll_interval_seconds = poll_interval_seconds
        self._groups: dict[str, OCOGroup] = {}

    async def submit(self, leg_a: OrderRequest, leg_b: OrderRequest) -> OCOGroup:
        """
        Submits both legs as pending orders (e.g. a breakout OCO: buy-stop above
        resistance + sell-stop below support). Returns the group immediately;
        call `watch()` (typically as a background task) to enforce the OCO behavior.
        """
        group_id = str(uuid.uuid4())
        group = OCOGroup(group_id=group_id, leg_a_request=leg_a, leg_b_request=leg_b)

        try:
            result_a = await self.broker.place_order(leg_a)
            group.leg_a_broker_order_id = result_a.broker_order_id
            result_b = await self.broker.place_order(leg_b)
            group.leg_b_broker_order_id = result_b.broker_order_id
        except BrokerOrderError:
            # If the second leg fails to place, cancel the first rather than leaving
            # a naked, un-paired order sitting on the account.
            if group.leg_a_broker_order_id:
                await self.broker.cancel_order(group.leg_a_broker_order_id)
            group.status = OCOStatus.error
            self._groups[group_id] = group
            raise

        self._groups[group_id] = group
        return group

    async def watch(self, group_id: str, max_wait_seconds: float = 3600.0) -> OCOGroup:
        """
        Polls both legs' fill status until one fills (then cancels the other) or the
        max wait elapses (then cancels both — an OCO that never triggers shouldn't
        sit open indefinitely).
        """
        group = self._groups[group_id]
        elapsed = 0.0

        while elapsed < max_wait_seconds:
            open_positions = await self.broker.get_open_positions()
            filled_a = any(p.broker_position_id == group.leg_a_broker_order_id for p in open_positions)
            filled_b = any(p.broker_position_id == group.leg_b_broker_order_id for p in open_positions)

            if filled_a and not filled_b:
                await self._cancel_leg(group.leg_b_broker_order_id)
                group.status = OCOStatus.leg_a_filled
                return group
            if filled_b and not filled_a:
                await self._cancel_leg(group.leg_a_broker_order_id)
                group.status = OCOStatus.leg_b_filled
                return group
            if filled_a and filled_b:
                # The race condition this module's docstring warns about — both legs
                # triggered in the same poll window. Log loudly; don't silently drop it.
                logger.error(
                    "OCO group %s: BOTH legs filled (race condition) — manual review needed",
                    group_id,
                )
                group.status = OCOStatus.error
                return group

            await asyncio.sleep(self.poll_interval_seconds)
            elapsed += self.poll_interval_seconds

        logger.warning("OCO group %s timed out after %.0fs — cancelling both legs", group_id, max_wait_seconds)
        await self._cancel_leg(group.leg_a_broker_order_id)
        await self._cancel_leg(group.leg_b_broker_order_id)
        group.status = OCOStatus.cancelled
        return group

    async def _cancel_leg(self, broker_order_id: str | None) -> None:
        if not broker_order_id:
            return
        try:
            await self.broker.cancel_order(broker_order_id)
        except BrokerOrderError as exc:
            # Already filled/expired between our check and the cancel call — not
            # fatal, just log it.
            logger.info("OCO leg %s could not be cancelled (likely already resolved): %s", broker_order_id, exc)
