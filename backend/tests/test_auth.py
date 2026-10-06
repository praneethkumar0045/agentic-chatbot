from collections.abc import Generator
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.app import create_app
from app.db.base import Base
from app.db.session import get_db
from app.models import RefreshToken
from app.security import auth as auth_security
from app.services import chat_service


@asynccontextmanager
async def chat_test_lifespan(app):
    app.state.chatbot = chat_service._build_chatbot(chat_service.llm, chat_service.tools)
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(auth_security.settings, "SECRET_KEY", "test-secret-key-" * 4)
    monkeypatch.setattr(auth_security.settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 15)
    monkeypatch.setattr(auth_security.settings, "REFRESH_TOKEN_EXPIRE_DAYS", 30)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with test_session() as session:
            yield session

    app = create_app(lifespan_context=chat_test_lifespan)
    app.state.test_session_factory = test_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client: TestClient, email: str = "person@example.com") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Test Person", "email": email, "password": "correct-horse-123"},
    )
    return response.json()


def test_register_normalizes_email_and_does_not_return_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": " Test Person ", "email": " Person@Example.com ", "password": "correct-horse-123"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "person@example.com"
    assert "password" not in response.json()
    assert "hashed_password" not in response.json()


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"name": "Another Person", "email": "PERSON@example.com", "password": "another-password"},
    )
    assert response.status_code == 409


def test_login_returns_access_and_refresh_tokens(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "PERSON@example.com", "password": "correct-horse-123"},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] == 900
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


def test_invalid_password_uses_generic_login_error(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_protected_me_requires_and_accepts_access_token(client: TestClient) -> None:
    register(client)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "correct-horse-123"},
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "person@example.com"
    assert "hashed_password" not in response.json()


def test_refresh_rotates_token_and_rejects_old_token(client: TestClient) -> None:
    register(client)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "correct-horse-123"},
    )
    old_refresh = login_response.json()["refresh_token"]
    with client.app.state.test_session_factory() as session:
        stored_token = session.scalar(select(RefreshToken))
        assert stored_token is not None
        assert stored_token.token_hash != old_refresh
        assert len(stored_token.token_hash) == 64
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert response.status_code == 200
    assert response.json()["refresh_token"] != old_refresh
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    register(client)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "correct-horse-123"},
    )
    refresh_token = login_response.json()["refresh_token"]
    response = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert response.status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401
