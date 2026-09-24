"""RISK-REGISTER R14: a client that drops a streaming chat mid-reply must not lose the reply.

Found by `infra/perf/load_test.py`, whose client stops reading after the first SSE event the way
a closed browser tab does. Every early-disconnected turn used to end with the user's message
persisted (or, when the drop landed early enough, nothing at all) and **no assistant message** —
while the client saw HTTP 200 throughout, so nothing signalled the loss.

Starlette ends a dropped stream two different ways and the fix has to handle both:
`GeneratorExit` (it calls `aclose()` on the body generator) and `asyncio.CancelledError` (it
cancels the task). The first draft of the fix caught only the second and still lost 61 of 91
replies under load, so both are pinned here.

httpx's `ASGITransport` buffers the whole response body, so an HTTP-level test cannot drop a
stream; these tests drive `chat_events` directly and close it, which is exactly what Starlette
does to it.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message, User
from app.modules.conversations import schemas, service
from app.modules.orgs.deps import _load_context
from app.worker import tasks as worker_tasks


async def _setup(client: AsyncClient, db_session: AsyncSession) -> tuple[Any, uuid.UUID]:
    signup = await client.post("/v1/auth/signup", json={"email": "drop@example.com", "password": "password123"})
    token = signup.json()["access_token"]
    org = (await client.post("/v1/orgs", json={"name": "Acme"}, headers={"Authorization": f"Bearer {token}"})).json()
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org["id"]}
    agent = (await client.post("/v1/agents", json={"name": "Bot"}, headers=headers)).json()
    await client.patch(
        f"/v1/agents/{agent['id']}/versions/1",
        json={"model_config": {"provider": "fake", "model": "fake"}}, headers=headers,
    )
    await client.post(f"/v1/agents/{agent['id']}/versions/1/publish", headers=headers)
    user = (await db_session.execute(select(User).where(User.email == "drop@example.com"))).scalar_one()
    ctx = await _load_context(db_session, user, uuid.UUID(org["id"]))
    return ctx, uuid.UUID(agent["id"])


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Capture `finalize_turn_task.delay(...)` instead of reaching a real broker."""
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(worker_tasks.finalize_turn_task, "delay", lambda *a: calls.append(a))
    return calls


async def _pull_first_token_then(gen: Any) -> None:
    async for ev in gen:
        if ev.type == "token":
            return


async def test_generator_close_mid_stream_hands_the_reply_to_the_worker(
    client: AsyncClient, db_session: AsyncSession, enqueued: list[tuple[Any, ...]]
) -> None:
    """`aclose()` -> `GeneratorExit`: the shape ~2/3 of dropped streams took under load."""
    ctx, agent_id = await _setup(client, db_session)
    gen = service.chat_events(db_session, ctx, agent_id, schemas.ChatRequest(message="hello", stream=True))
    await _pull_first_token_then(gen)
    await gen.aclose()

    assert len(enqueued) == 1
    conv_data, result_data, _latency, first_text = enqueued[0]
    assert first_text == "hello"
    assert result_data["content"].startswith("echo:")  # partial: the drop lands mid-reply
    assert conv_data["channel"] == "dashboard"
    assert conv_data["organization_id"] == str(ctx.org.id)


async def test_task_cancellation_mid_stream_hands_the_reply_to_the_worker(
    client: AsyncClient, db_session: AsyncSession, enqueued: list[tuple[Any, ...]]
) -> None:
    """`CancelledError`: the other shape (the session is left mid-flush, so it cannot be reused)."""
    ctx, agent_id = await _setup(client, db_session)
    gen = service.chat_events(db_session, ctx, agent_id, schemas.ChatRequest(message="hello", stream=True))
    await _pull_first_token_then(gen)
    with pytest.raises(asyncio.CancelledError):
        await gen.athrow(asyncio.CancelledError())

    assert len(enqueued) == 1
    assert enqueued[0][1]["content"].startswith("echo:")


async def test_a_stream_read_to_the_end_enqueues_nothing(
    client: AsyncClient, db_session: AsyncSession, enqueued: list[tuple[Any, ...]]
) -> None:
    """The happy path must be untouched — no second write, no duplicate reply."""
    ctx, agent_id = await _setup(client, db_session)
    async for _ev in service.chat_events(db_session, ctx, agent_id, schemas.ChatRequest(message="hello", stream=True)):
        pass
    assert enqueued == []
    replies = (
        await db_session.execute(
            select(Message).where(Message.role == "assistant", Message.organization_id == ctx.org.id)
        )
    ).scalars().all()
    assert [m.content for m in replies] == ["echo: hello"]


async def test_worker_appends_the_reply_when_the_conversation_survived(
    client: AsyncClient, db_session: AsyncSession, enqueued: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, agent_id = await _setup(client, db_session)
    gen = service.chat_events(db_session, ctx, agent_id, schemas.ChatRequest(message="hello", stream=True))
    await _pull_first_token_then(gen)
    await gen.aclose()
    conv_data, result_data, latency, first_text = enqueued[0]

    await _run_worker_task(db_session, monkeypatch, conv_data, result_data, latency, first_text)

    conv_id = uuid.UUID(conv_data["id"])
    replies = (
        await db_session.execute(
            select(Message).where(Message.role == "assistant", Message.conversation_id == conv_id)
        )
    ).scalars().all()
    assert len(replies) == 1 and (replies[0].content or "").startswith("echo:")
    users = (
        await db_session.execute(select(Message).where(Message.role == "user", Message.conversation_id == conv_id))
    ).scalars().all()
    assert len(users) == 1  # not duplicated


async def test_worker_recreates_a_conversation_that_never_committed(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The early-drop case: even the conversation and the visitor's message were lost with the
    request's transaction, so the task rebuilds both under the SAME id the request had picked."""
    ctx, _agent_id = await _setup(client, db_session)
    conv_id = uuid.uuid4()
    conv_data = {
        "id": str(conv_id), "organization_id": str(ctx.org.id), "agent_id": str(_agent_id),
        "channel": "dashboard", "channel_user_id": None, "contact_id": None, "external_id": None,
    }
    result_data = {"content": "echo: hi", "provider": "fake", "model": "fake"}

    await _run_worker_task(db_session, monkeypatch, conv_data, result_data, 5, "hi")

    conv = await db_session.get(Conversation, conv_id)
    assert conv is not None and conv.channel == "dashboard"
    msgs = (await db_session.execute(select(Message).where(Message.conversation_id == conv_id))).scalars().all()
    assert sorted((m.role, m.content) for m in msgs) == [("assistant", "echo: hi"), ("user", "hi")]


async def test_worker_writes_no_empty_reply_when_nothing_was_generated(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, agent_id = await _setup(client, db_session)
    conv_id = uuid.uuid4()
    conv_data = {
        "id": str(conv_id), "organization_id": str(ctx.org.id), "agent_id": str(agent_id),
        "channel": "dashboard", "channel_user_id": None, "contact_id": None, "external_id": None,
    }
    await _run_worker_task(db_session, monkeypatch, conv_data, {}, 1, "hi")

    msgs = (await db_session.execute(select(Message).where(Message.conversation_id == conv_id))).scalars().all()
    assert [m.role for m in msgs] == ["user"]  # the visitor's message is kept; no blank assistant row


async def _run_worker_task(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
    conv_data: dict[str, Any], result_data: dict[str, Any], latency: int, first_text: str,
) -> None:
    """Run the task body against the test's rolled-back session instead of a real committing one
    (the worker's `SessionFactory` would leak rows past the test's transaction)."""

    class _Ctx:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(worker_tasks, "SessionFactory", lambda: _Ctx())
    monkeypatch.setattr(db_session, "commit", db_session.flush)
    await worker_tasks._run_finalize_turn(conv_data, result_data, latency, first_text)
