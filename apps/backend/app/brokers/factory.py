"""
Broker adapter factory + selection logic.

Implements the comparison the spec asked for: given what's actually configured/available
in this environment, pick the best real adapter rather than hardcoding one.

Decision rule (see docs/broker-comparison.md for the full writeup):
1. If MT5 credentials are set AND the MetaTrader5 package is importable (i.e. we're
   running on Windows with a terminal available) -> use MT5Adapter. It's free and has
   the lowest latency (local IPC to the terminal), so it wins whenever it's viable.
2. Otherwise, if a MetaApi token + account id are set -> use MetaApiAdapter. This is
   the only viable path from a Linux container/VPS, at the cost of MetaApi's cloud
   latency and free-tier account/rate limits.
3. If neither is configured -> raise, with a message telling the operator which env
   vars to set. We never silently fall back to a fake/mock adapter.
"""
from __future__ import annotations

from app.brokers.base import BrokerAdapter, BrokerConnectionError
from app.core.config import Settings


def get_broker_adapter(settings: Settings) -> BrokerAdapter:
    mt5_configured = bool(settings.mt5_login and settings.mt5_password and settings.mt5_server)
    metaapi_configured = bool(settings.metaapi_token and settings.metaapi_account_id)

    if mt5_configured:
        try:
            from app.brokers.mt5_adapter import MT5Adapter

            return MT5Adapter(
                login=int(settings.mt5_login),
                password=settings.mt5_password,
                server=settings.mt5_server,
                terminal_path=settings.mt5_terminal_path,
            )
        except BrokerConnectionError:
            if not metaapi_configured:
                raise
            # MT5 package unavailable on this host (e.g. running in a Linux container)
            # and MetaApi is configured -> fall through to it.

    if metaapi_configured:
        from app.brokers.metaapi_adapter import MetaApiAdapter

        return MetaApiAdapter(token=settings.metaapi_token, account_id=settings.metaapi_account_id)

    raise BrokerConnectionError(
        "No broker configured. Set MT5_LOGIN/MT5_PASSWORD/MT5_SERVER (requires a "
        "Windows host with a running MT5 terminal) or METAAPI_TOKEN/METAAPI_ACCOUNT_ID "
        "(works from any container) in your .env."
    )


def get_adapter_for_account(account, settings: Settings) -> BrokerAdapter:
    """
    Builds a broker adapter for a specific user's connected TradingAccount row,
    decrypting its stored credentials, rather than the single global-settings
    adapter above (which is meant for platform-level ops/testing). This is what
    app/api/orders.py uses to execute a given user's trade against their own account.
    """
    from app.core.crypto import decrypt_broker_credentials
    from app.models.account import BrokerType

    creds = decrypt_broker_credentials(account.encrypted_credentials)

    if account.broker_type == BrokerType.mt5:
        from app.brokers.mt5_adapter import MT5Adapter

        return MT5Adapter(
            login=int(account.broker_login),
            password=creds["password"],
            server=account.broker_server,
            terminal_path=settings.mt5_terminal_path,
        )

    if account.broker_type == BrokerType.metaapi:
        from app.brokers.metaapi_adapter import MetaApiAdapter

        if not settings.metaapi_token:
            raise BrokerConnectionError("METAAPI_TOKEN is not configured on this server.")
        # For MetaApi, `broker_login` on the account row stores the MetaApi account id
        # (the account was provisioned in MetaApi's dashboard, not with a raw MT login).
        return MetaApiAdapter(token=settings.metaapi_token, account_id=account.broker_login)

    if account.broker_type == BrokerType.paper:
        from app.brokers.paper_adapter import PaperTradingAdapter

        return PaperTradingAdapter(settings)

    raise BrokerConnectionError(f"Unsupported broker_type for live execution: {account.broker_type}")
