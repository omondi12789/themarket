"""
HashiCorp Vault integration, replacing plaintext .env secrets in production the same
way infra/terraform/secrets.tf's AWS Secrets Manager pattern does for an AWS
deployment — this is the Vault-specific implementation of that same substitution
(env var -> secrets client), for teams that run Vault instead of/alongside AWS.

Design: `get_secret()` tries Vault first (if VAULT_ADDR + VAULT_TOKEN are set), and
falls back to the equivalent environment variable if Vault is unreachable or unset.
This means local dev (.env file, no Vault) and production (Vault, no .env) both work
against the same call sites in app/core/config.py without an if/else at every
call site — the fallback logic lives in one place.

Auth method: token auth (VAULT_TOKEN) is the simplest to wire up and matches most
CI/local-dev setups; production Vault deployments more commonly use AppRole or
Kubernetes auth. Swapping auth methods only touches `_get_vault_client()` below.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

try:
    import hvac
except ImportError:  # pragma: no cover — hvac is in requirements.txt but kept optional at import time
    hvac = None


class VaultUnavailableError(Exception):
    pass


@lru_cache
def _get_vault_client():
    if hvac is None:
        raise VaultUnavailableError("hvac package not installed")

    vault_addr = os.environ.get("VAULT_ADDR")
    vault_token = os.environ.get("VAULT_TOKEN")
    if not vault_addr or not vault_token:
        raise VaultUnavailableError("VAULT_ADDR / VAULT_TOKEN not configured")

    client = hvac.Client(url=vault_addr, token=vault_token)
    if not client.is_authenticated():
        raise VaultUnavailableError("Vault client failed to authenticate — check VAULT_TOKEN")

    return client


def get_secret(vault_path: str, vault_key: str, env_fallback_var: str) -> str | None:
    """
    Reads a KV v2 secret from Vault at `vault_path`, field `vault_key` (e.g.
    vault_path="themarket-ai/production/database", vault_key="url"). Falls back to
    `env_fallback_var` (a plain os.environ lookup) if Vault isn't configured/reachable
    — this fallback is what makes local development work without running Vault at all.
    """
    try:
        client = _get_vault_client()
        response = client.secrets.kv.v2.read_secret_version(path=vault_path)
        value = response["data"]["data"].get(vault_key)
        if value is not None:
            return value
        logger.warning("Vault path %s has no key '%s' — falling back to %s", vault_path, vault_key, env_fallback_var)
    except VaultUnavailableError as exc:
        logger.info("Vault unavailable (%s) — falling back to %s", exc, env_fallback_var)
    except Exception:
        logger.exception("unexpected error reading Vault secret at %s — falling back to %s", vault_path, env_fallback_var)

    return os.environ.get(env_fallback_var)


def get_secret_or_raise(vault_path: str, vault_key: str, env_fallback_var: str) -> str:
    value = get_secret(vault_path, vault_key, env_fallback_var)
    if value is None:
        raise RuntimeError(
            f"no value found for secret '{vault_key}' at Vault path '{vault_path}' "
            f"or environment variable '{env_fallback_var}'"
        )
    return value
