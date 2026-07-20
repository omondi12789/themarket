"""
Password hashing, JWT issuance/verification, and TOTP (2FA) helpers.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


# ---------- Passwords ----------

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ---------- JWT ----------

def _create_token(subject: UUID, expires_delta: timedelta, secret: str, token_type: TokenType) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID) -> str:
    return _create_token(
        user_id,
        timedelta(minutes=settings.access_token_expire_minutes),
        settings.jwt_secret,
        "access",
    )


def create_refresh_token(user_id: UUID) -> str:
    return _create_token(
        user_id,
        timedelta(days=settings.refresh_token_expire_days),
        settings.jwt_refresh_secret,
        "refresh",
    )


class TokenError(Exception):
    pass


def decode_token(token: str, token_type: TokenType) -> UUID:
    secret = settings.jwt_secret if token_type == "access" else settings.jwt_refresh_secret
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenError("invalid or expired token") from exc

    if payload.get("type") != token_type:
        raise TokenError(f"expected a {token_type} token")

    return UUID(payload["sub"])


# ---------- TOTP (2FA) ----------

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.totp_issuer)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)
