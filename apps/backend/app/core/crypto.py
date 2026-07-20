"""
Encrypts broker credentials before they're persisted (see TradingAccount.encrypted_credentials).
Uses Fernet (AES-128-CBC + HMAC, from the `cryptography` package) — authenticated
symmetric encryption, appropriate for "the app needs to decrypt this to place live
orders" (as opposed to password hashing, which is one-way and used for user login
passwords in app/core/security.py).
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    key = getattr(settings, "fernet_key", None)
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and set it in .env — never hardcode it in source."
        )
    return Fernet(key.encode())


def encrypt_broker_credentials(credentials: dict) -> str:
    payload = json.dumps(credentials).encode()
    return _get_fernet().encrypt(payload).decode()


def decrypt_broker_credentials(token: str) -> dict:
    payload = _get_fernet().decrypt(token.encode())
    return json.loads(payload.decode())
