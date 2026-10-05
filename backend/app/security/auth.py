import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core import settings


password_hash = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def _secret_key() -> str:
    secret = settings.SECRET_KEY
    if not secret or len(secret.encode("utf-8")) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 bytes.")
    return secret


def create_access_token(user_id: int) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": expires_at,
        },
        _secret_key(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, expires_at


def decode_access_token(token: str) -> int:
    payload = jwt.decode(
        token,
        _secret_key(),
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "iat", "exp", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type.")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdecimal():
        raise jwt.InvalidTokenError("Invalid subject.")
    return int(subject)


def create_refresh_token() -> tuple[str, str]:
    return secrets.token_urlsafe(48), str(uuid.uuid4())


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
