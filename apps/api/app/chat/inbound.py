"""Run one inbound turn for a conversation — the shared core behind the widget and channels.

The widget streams the events; channel senders consume the turn and forward the final text.
When a conversation is handed off to a human, the user's message is still persisted but the
bot does not generate (the operator replies via the inbox).
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.assembly import build_messages
from app.chat.handoff import trigger_handoff, wants_handoff
from app.chat.runtime import TurnResult, run_turn
from app.core.config import settings
from app.llm.types import StreamEvent
from app.models import Agent, AgentVersion, Conversation, Message
from app.rag.agent_retrieval import retrieve_for_version


class InboundTurn:
    """One inbound message → bot turn. Read `handed_off` / `result` / `assistant_message` after."""

    def __init__(
        self,
        session: AsyncSession,
        agent: Agent,
        version: AgentVersion,
        conversation: Conversation,
        message: str,
    ) -> None:
        self.session = session
        self.agent = agent
        self.version = version
        self.conversation = conversation
        self.message = message
        self.result = TurnResult()
        self.handed_off = False
        self.assistant_message: Message | None = None

    async def events(self) -> AsyncIterator[StreamEvent]:
        # Import here to avoid a module cycle (conversations.service imports chat.*).
        from app.modules.conversations.service import (
            _build_chat_request,
            _finalize_turn,
            _load_history,
            _persist_user_message,
            _resolve_provider,
        )
        from app.tools.service import build_tooling

        session = self.session
        conv = self.conversation
        org_id = conv.organization_id

        history = await _load_history(session, conv.id)
        _persist_user_message(session, conv, self.message)
        await session.flush()

        # Paused for a human — persist the visitor message, but the bot stays silent.
        if conv.status == "handoff":
            self.handed_off = True
            conv.last_message_at = dt.datetime.now(tz=dt.UTC)
            await session.flush()
            return

        # Keyword handoff: the visitor is asking for a human.
        features = self.version.features or {}
        if features.get("handoff_enabled") and wants_handoff(self.message):
            await trigger_handoff(session, conv, requested_by="user", reason="keyword")
            self.handed_off = True
            canned = (
                self.version.fallback_message
                or "Let me connect you with a teammate — someone will be with you shortly."
            )
            msg = Message(
                conversation_id=conv.id,
                organization_id=conv.organization_id,
                role="assistant",
                content=canned,
                provider="system",
            )
            session.add(msg)
            conv.last_message_at = dt.datetime.now(tz=dt.UTC)
            await session.flush()
            self.assistant_message = msg
            self.result.content = canned
            yield StreamEvent(type="token", delta=canned)
            yield StreamEvent(type="done", finish_reason="handoff")
            yield StreamEvent(type="message", message_id=str(msg.id))
            return

        context_block, citations = await retrieve_for_version(session, org_id, self.version, self.message)
        messages = build_messages(
            system_prompt=self.version.system_prompt,
            context_block=context_block,
            memory_summary=conv.memory_summary,
            history=history,
            user_message=self.message,
            window_messages=settings.memory_window_messages,
        )
        provider_name = (self.version.model_config_json or {}).get("provider", "fake")
        provider = await _resolve_provider(session, org_id, self.agent, provider_name)
        req = _build_chat_request(self.version, messages, stream=True)

        specs, executor = await build_tooling(session, org_id, self.agent, self.version, conv.id)
        if specs and executor is not None and provider.supports_tools():
            req.tools = specs
        else:
            executor = None

        t0 = time.perf_counter()
        async for ev in run_turn(
            provider, req, [c.model_dump(mode="json") for c in citations], self.result,
            executor=executor, max_iters=settings.tool_max_iterations,
        ):
            yield ev
        latency_ms = int((time.perf_counter() - t0) * 1000)
        self.assistant_message = await _finalize_turn(session, conv, self.result, latency_ms, self.message)
        yield StreamEvent(type="message", message_id=str(self.assistant_message.id))

    async def run(self) -> None:
        """Non-streaming: run the turn to completion (channels send `self.result.content`)."""
        async for _ev in self.events():
            pass
