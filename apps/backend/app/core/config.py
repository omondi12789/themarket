"""
Centralized application settings.

All secrets/config come from environment variables (see .env.example at repo root).
Nothing sensitive is hardcoded here.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.vault import get_secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"

    # Core infra
    database_url: str
    database_read_replica_url: str | None = None
    redis_url: str

    # Auth
    jwt_secret: str
    jwt_refresh_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    totp_issuer: str = "THEMARKET-AI"
    fernet_key: str | None = None  # encrypts broker credentials at rest; see app/core/crypto.py

    # Market data providers
    polygon_api_key: str | None = None
    twelvedata_api_key: str | None = None
    alphavantage_api_key: str | None = None
    finnhub_api_key: str | None = None

    # News / sentiment providers
    newsapi_key: str | None = None
    finnhub_news_key: str | None = None

    # MT5 (official python package, requires running terminal)
    mt5_login: str | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_terminal_path: str | None = None

    # MetaApi (cloud fallback)
    metaapi_token: str | None = None
    metaapi_account_id: str | None = None

    ai_engine_url: str = "http://ai-engine:8100"

    # Vault: which KV mount/path prefix to read secrets from when VAULT_ADDR is set.
    # e.g. "themarket-ai/production" — combined with a field name for the vault_key.
    vault_secret_path_prefix: str | None = None

    def apply_vault_overrides(self) -> "Settings":
        """
        Optionally overrides the handful of genuinely sensitive fields with values
        read from Vault (see app/core/vault.py), when VAULT_ADDR/VAULT_TOKEN and
        vault_secret_path_prefix are configured. No-op (returns self unchanged) in
        any environment without Vault configured — this is what keeps local dev
        working purely off .env with zero Vault dependency.
        """
        if not self.vault_secret_path_prefix:
            return self

        prefix = self.vault_secret_path_prefix
        overrides = {
            "database_url": get_secret(f"{prefix}/database", "url", "DATABASE_URL"),
            "redis_url": get_secret(f"{prefix}/redis", "url", "REDIS_URL"),
            "jwt_secret": get_secret(f"{prefix}/auth", "jwt_secret", "JWT_SECRET"),
            "jwt_refresh_secret": get_secret(f"{prefix}/auth", "jwt_refresh_secret", "JWT_REFRESH_SECRET"),
            "fernet_key": get_secret(f"{prefix}/auth", "fernet_key", "FERNET_KEY"),
        }
        for field, value in overrides.items():
            if value is not None:
                setattr(self, field, value)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings().apply_vault_overrides()
