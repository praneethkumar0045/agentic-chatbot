from datetime import timedelta, timezone

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import settings
from app.models import RefreshToken, User
from app.models.user import utc_now
from app.schemas.auth import TokenResponse
from app.security.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


INVALID_CREDENTIALS = "Invalid email or password"


def _issue_token_pair(db: Session, user: User) -> TokenResponse:
    access_token, _ = create_access_token(user.id)
    refresh_token, identifier = create_refresh_token()
    now = utc_now()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_identifier=identifier,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def register_user(db: Session, *, name: str, email: str, password: str) -> User:
    user = User(name=name, email=email, hashed_password=hash_password(password))
    try:
        with db.begin():
            db.add(user)
            db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.") from exc
    return user


def login(db: Session, *, email: str, password: str) -> TokenResponse:
    with db.begin():
        user = db.scalar(select(User).where(User.email == email))
        if user is None or not user.is_active or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=INVALID_CREDENTIALS,
                headers={"WWW-Authenticate": "Bearer"},
            )
        user.last_login_at = utc_now()
        tokens = _issue_token_pair(db, user)
    return tokens


def refresh(db: Session, raw_token: str) -> TokenResponse:
    token_hash = hash_refresh_token(raw_token)
    with db.begin():
        stored_token = db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
        now = utc_now()
        expires_at = stored_token.expires_at if stored_token is not None else None
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if (
            stored_token is None
            or stored_token.revoked_at is not None
            or expires_at is None
            or expires_at <= now
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
        user = db.get(User, stored_token.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
        stored_token.revoked_at = now
        tokens = _issue_token_pair(db, user)
    return tokens


def logout(db: Session, raw_token: str) -> None:
    with db.begin():
        stored_token = db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
            .with_for_update()
        )
        now = utc_now()
        if stored_token is None or stored_token.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
        expires_at = stored_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
        stored_token.revoked_at = now


def authenticate_access_token(db: Session, raw_token: str) -> User:
    try:
        user_id = decode_access_token(raw_token)
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user.")
    return user
