from collections.abc import Generator
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.app import create_app
from app.db.base import Base
from app.db.session import get_db
from app.models import Conversation
from app.security import auth as auth_security
from app.services import chat_service


@asynccontextmanager
async def chat_test_lifespan(app):
    app.state.chatbot = chat_service._build_chatbot(chat_service.llm, chat_service.tools)
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(auth_security.settings, "SECRET_KEY", "test-secret-key-" * 4)
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
    app.dependency_overrides[get_db] = override_get_db
    app.state.test_session_factory = test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def create_user(client: TestClient, email: str) -> str:
    registered = client.post(
        "/api/v1/auth/register",
        json={"name": "Conversation User", "email": email, "password": "correct-horse-123"},
    )
    assert registered.status_code == 201
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_conversation_routes_require_authentication(client: TestClient) -> None:
    assert client.post("/api/v1/conversations", json={}).status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401
    assert client.get("/api/v1/conversations/thread").status_code == 401
    assert client.delete("/api/v1/conversations/thread").status_code == 401
    assert client.post(
        "/api/v1/chat",
        json={"thread_id": "thread", "messages": [{"role": "user", "content": "Hello"}]},
    ).status_code == 401
    assert client.post(
        "/api/v1/chat/stream",
        json={"thread_id": "thread", "messages": [{"role": "user", "content": "Hello"}]},
    ).status_code == 401


def test_chat_requires_thread_id(client: TestClient) -> None:
    token = create_user(client, "thread-required@example.com")
    payload = {"messages": [{"role": "user", "content": "Hello"}]}
    assert client.post("/api/v1/chat", json=payload, headers=auth(token)).status_code == 422
    assert client.post("/api/v1/chat/stream", json=payload, headers=auth(token)).status_code == 422


def test_user_can_create_list_read_and_delete_conversation(client: TestClient) -> None:
    token = create_user(client, "first@example.com")
    headers = auth(token)
    created = client.post("/api/v1/conversations", json={}, headers=headers)
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["id"]
    assert conversation["title"] == "New conversation"

    listed = client.get("/api/v1/conversations", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [conversation["id"]]

    detail = client.get(f"/api/v1/conversations/{conversation['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["messages"] == []

    deleted = client.delete(f"/api/v1/conversations/{conversation['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/conversations/{conversation['id']}", headers=headers).status_code == 404


def test_conversation_is_forbidden_to_another_user(client: TestClient) -> None:
    first_token = create_user(client, "first@example.com")
    second_token = create_user(client, "second@example.com")
    created = client.post("/api/v1/conversations", json={}, headers=auth(first_token))
    thread_id = created.json()["id"]

    assert client.get(f"/api/v1/conversations/{thread_id}", headers=auth(second_token)).status_code == 403
    assert client.delete(f"/api/v1/conversations/{thread_id}", headers=auth(second_token)).status_code == 403
    assert client.get("/api/v1/conversations", headers=auth(second_token)).json() == []


def test_chat_requires_owned_thread_and_uses_conversation_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.router as chat_router

    first_token = create_user(client, "first@example.com")
    second_token = create_user(client, "second@example.com")
    thread_id = client.post("/api/v1/conversations", json={}, headers=auth(first_token)).json()["id"]
    calls: list[str] = []
    monkeypatch.setattr(
        chat_router.chat_service,
        "chat",
        lambda messages, thread_id, **kwargs: calls.append(thread_id) or [],
    )
    payload = {"thread_id": thread_id, "messages": [{"role": "user", "content": "Hello Medha"}]}

    assert client.post("/api/v1/chat", json=payload).status_code == 401
    forbidden = client.post("/api/v1/chat", json=payload, headers=auth(second_token))
    assert forbidden.status_code == 403
    assert calls == []

    response = client.post("/api/v1/chat", json=payload, headers=auth(first_token))
    assert response.status_code == 200
    assert calls == [thread_id]
    with client.app.state.test_session_factory() as session:
        conversation = session.scalar(select(Conversation).where(Conversation.id == thread_id))
        assert conversation is not None
        assert conversation.title == "Hello Medha"


def test_chat_persists_history_and_reuses_it_for_follow_up_turns(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.router as chat_router

    token = create_user(client, "history@example.com")
    headers = auth(token)
    thread_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
    received_histories: list[list[tuple[str, str]]] = []

    def fake_chat(messages, thread_id, *, fallback_history=None, **kwargs):
        full_history = [*(fallback_history or []), *messages]
        received_histories.append([(message.role, message.content) for message in full_history])
        history = [
            HumanMessage(content=message.content)
            if message.role == "user"
            else AIMessage(content=message.content)
            for message in messages
        ]
        return [*history, AIMessage(content=f"Answer {len(received_histories)}")]

    monkeypatch.setattr(chat_router.chat_service, "chat", fake_chat)

    first_response = client.post(
        "/api/v1/chat",
        json={"thread_id": thread_id, "messages": [{"role": "user", "content": "First question"}]},
        headers=headers,
    )
    second_response = client.post(
        "/api/v1/chat",
        json={"thread_id": thread_id, "messages": [{"role": "user", "content": "Follow-up"}]},
        headers=headers,
    )
    detail = client.get(f"/api/v1/conversations/{thread_id}", headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert received_histories == [
        [("user", "First question")],
        [
            ("user", "First question"),
            ("assistant", "Answer 1"),
            ("user", "Follow-up"),
        ],
    ]
    assert detail.json()["messages"] == [
        {"role": "user", "content": "First question", "metadata": None},
        {"role": "assistant", "content": "Answer 1", "metadata": None},
        {"role": "user", "content": "Follow-up", "metadata": None},
        {"role": "assistant", "content": "Answer 2", "metadata": None},
    ]


def test_stream_chat_checks_ownership_before_starting_stream(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.router as chat_router

    first_token = create_user(client, "first@example.com")
    second_token = create_user(client, "second@example.com")
    thread_id = client.post("/api/v1/conversations", json={}, headers=auth(first_token)).json()["id"]
    calls: list[tuple[str, list[tuple[str, str]]]] = []

    def fake_stream(messages, thread_id, *, fallback_history=None, **kwargs):
        calls.append((thread_id, [(message.role, message.content) for message in messages]))
        yield type(
            "ToolCallChunk",
            (),
            {
                "content": "",
                "type": "AIMessageChunk",
                "tool_call_chunks": [{"name": "tavily_search"}],
            },
        )()
        yield type(
            "ToolChunk",
            (),
            {
                "content": "Search result should not be shown as assistant text",
                "type": "ToolMessageChunk",
                "tool_call_id": "search-1",
            },
        )()
        yield type("Chunk", (), {"content": "ok", "type": "message"})()

    monkeypatch.setattr(chat_router.chat_service, "stream_chat", fake_stream)
    payload = {"thread_id": thread_id, "messages": [{"role": "user", "content": "Hello"}]}

    forbidden = client.post("/api/v1/chat/stream", json=payload, headers=auth(second_token))
    assert forbidden.status_code == 403
    assert calls == []

    response = client.post("/api/v1/chat/stream", json=payload, headers=auth(first_token))
    assert response.status_code == 200
    assert response.text == (
        'data: {"content": "Searching the web...", "type": "status"}\n\n'
        'data: {"content": "ok", "type": "message"}\n\n'
    )
    assert "Search result should not be shown as assistant text" not in response.text
    assert calls == [(thread_id, [("user", "Hello")])]

    follow_up = client.post(
        "/api/v1/chat/stream",
        json={"thread_id": thread_id, "messages": [{"role": "user", "content": "Follow-up"}]},
        headers=auth(first_token),
    )
    assert follow_up.status_code == 200
    assert calls[-1] == (
        thread_id,
        [("user", "Follow-up")],
    )
    detail = client.get(f"/api/v1/conversations/{thread_id}", headers=auth(first_token))
    assert detail.json()["messages"] == [
        {"role": "user", "content": "Hello", "metadata": None},
        {"role": "assistant", "content": "ok", "metadata": None},
        {"role": "user", "content": "Follow-up", "metadata": None},
        {"role": "assistant", "content": "ok", "metadata": None},
    ]


@pytest.mark.parametrize(
    ("decision", "expected_answer"),
    [("approve", "Answer using the search"), ("reject", "Answer without the search")],
)
def test_tavily_approval_resumes_same_thread_without_duplicate_messages(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    expected_answer: str,
) -> None:
    import app.api.v1.router as chat_router

    token = create_user(client, f"approval-{decision}@example.com")
    headers = auth(token)
    thread_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
    approvals: dict[str, dict[str, str]] = {}
    calls: list[tuple[str, list[tuple[str, str]], str | None]] = []
    monkeypatch.setattr(
        chat_router.chat_service,
        "pending_approval",
        lambda chatbot, current_thread_id: approvals.get(current_thread_id),
    )

    def fake_stream(
        messages,
        thread_id,
        *,
        approval_decision=None,
        **kwargs,
    ):
        calls.append(
            (
                thread_id,
                [(message.role, message.content) for message in messages],
                approval_decision,
            )
        )
        if approval_decision is None:
            approvals[thread_id] = {
                "type": "approval_required",
                "tool": "tavily_search",
                "query": "current weather",
            }
            yield approvals[thread_id]
            return

        assert approval_decision in {"approve", "reject"}
        approvals.pop(thread_id)
        yield type("Chunk", (), {"content": expected_answer, "type": "AIMessageChunk"})()

    monkeypatch.setattr(chat_router.chat_service, "stream_chat", fake_stream)

    initial = client.post(
        "/api/v1/chat/stream",
        json={
            "thread_id": thread_id,
            "messages": [{"role": "user", "content": "What is the current weather?"}],
        },
        headers=headers,
    )

    assert initial.status_code == 200
    assert f"event: approval_required\ndata: " in initial.text
    assert '"tool": "tavily_search"' in initial.text
    assert '"query": "current weather"' in initial.text
    assert client.get(f"/api/v1/conversations/{thread_id}", headers=headers).json()[
        "pending_approval"
    ] == {
        "type": "approval_required",
        "tool": "tavily_search",
        "query": "current weather",
    }

    resumed = client.post(
        "/api/v1/chat/stream",
        json={"thread_id": thread_id, "messages": [], "approval_decision": decision},
        headers=headers,
    )
    detail = client.get(f"/api/v1/conversations/{thread_id}", headers=headers).json()

    assert resumed.status_code == 200
    assert expected_answer in resumed.text
    assert detail["pending_approval"] is None
    assert [(message["role"], message["content"]) for message in detail["messages"]] == [
        ("user", "What is the current weather?"),
        ("assistant", expected_answer),
    ]
    assert calls == [
        (
            thread_id,
            [("user", "What is the current weather?")],
            None,
        ),
        (thread_id, [], decision),
    ]
