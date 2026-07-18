"""Chat + conversation routes (docs/04 §Chat)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.session import SessionFactory, get_session
from app.models import User
from app.modules.conversations import schemas, service
from app.modules.orgs.deps import OrgContext, _load_context, current_org

log = get_logger("conversations.router")

router = APIRouter(tags=["conversations"])


# ── Chat ─────────────────────────────────────────────────────────────────────────
@router.post("/v1/agents/{agent_id}/chat", response_model=None)
async def chat(
    agent_id: uuid.UUID,
    data: schemas.ChatRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> StreamingResponse | dict[str, Any]:
    if data.stream:
        return StreamingResponse(
            service.chat_sse(session, ctx, agent_id, data), media_type="text/event-stream"
        )
    return await service.chat_once(session, ctx, agent_id, data)


@router.websocket("/v1/agents/{agent_id}/chat/ws")
async def chat_ws(websocket: WebSocket, agent_id: uuid.UUID) -> None:
    """Bidirectional chat. Auth via `?token=<access>&org_id=<uuid>` query params."""
    token = websocket.query_params.get("token")
    org_raw = websocket.query_params.get("org_id")
    await websocket.accept()

    claims = decode_access_token(token) if token else None
    if claims is None or not org_raw:
        await websocket.close(code=4401)
        return
    try:
        user_id = uuid.UUID(claims["sub"])
        org_id = uuid.UUID(org_raw)
    except (KeyError, ValueError):
        await websocket.close(code=4401)
        return

    # Each socket owns a committing session, separate from the HTTP request scope.
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active or user.deleted_at is not None:
            await websocket.close(code=4401)
            return
        try:
            ctx = await _load_context(session, user, org_id)
        except Exception:
            await websocket.close(code=4403)
            return

        try:
            while True:
                payload = await websocket.receive_json()
                try:
                    data = schemas.ChatRequest(**payload)
                except Exception as exc:  # malformed client frame
                    await websocket.send_json({"type": "error", "error": f"bad request: {exc}"})
                    continue
                async for ev in service.chat_events(session, ctx, agent_id, data):
                    await websocket.send_text(ev.model_dump_json())
                await session.commit()
        except WebSocketDisconnect:
            return
        except Exception as exc:  # surface + close on unexpected failure
            log.warning("chat_ws_error", error=str(exc))
            await session.rollback()
            await websocket.close(code=1011)


# ── Conversations ──────────────────────────────────────────────────────────────────
conversations = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@conversations.get("", response_model=list[schemas.ConversationOut])
async def list_conversations(
    agent_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.ConversationOut]:
    return await service.list_conversations(session, ctx, agent_id)


@conversations.get("/{cid}", response_model=schemas.ConversationDetail)
async def get_conversation(
    cid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ConversationDetail:
    return await service.get_conversation(session, ctx, cid)


@conversations.get("/{cid}/messages", response_model=list[schemas.MessageOut])
async def get_messages(
    cid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.MessageOut]:
    return await service.get_messages(session, ctx, cid)


@conversations.patch("/{cid}", response_model=schemas.ConversationOut)
async def update_conversation(
    cid: uuid.UUID,
    data: schemas.UpdateConversationRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ConversationOut:
    return await service.update_conversation(session, ctx, cid, data)


@conversations.delete("/{cid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    cid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_conversation(session, ctx, cid)


router.include_router(conversations)
