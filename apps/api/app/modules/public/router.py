"""Public widget/channel routes (docs/04 §Public chat). No dashboard auth."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.ratelimit import rate_limit
from app.db.session import SessionFactory, get_session
from app.models import Conversation
from app.modules.public import schemas, service
from app.realtime.hub import conv_topic, hub

log = get_logger("public")

router = APIRouter(prefix="/v1/public", tags=["public"])


@router.get("/agents/{public_key}/config", response_model=schemas.PublicConfig)
async def get_config(
    public_key: str, session: AsyncSession = Depends(get_session)
) -> schemas.PublicConfig:
    return await service.get_config(session, public_key)


@router.post(
    "/agents/{public_key}/chat",
    response_model=None,
    dependencies=[Depends(rate_limit("public_chat", limit=60, window=60))],
)
async def public_chat(
    public_key: str,
    data: schemas.PublicChatRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse | dict[str, Any]:
    visitor_id = service.visitor_id_for(data)
    if data.stream:
        return StreamingResponse(
            service.public_chat_sse(session, public_key, data, visitor_id),
            media_type="text/event-stream",
        )
    return await service.public_chat_once(session, public_key, data, visitor_id)


@router.websocket("/agents/{public_key}/ws")
async def public_chat_ws(websocket: WebSocket, public_key: str) -> None:
    await websocket.accept()
    async with SessionFactory() as session:
        try:
            while True:
                payload = await websocket.receive_json()
                try:
                    data = schemas.PublicChatRequest(**payload)
                except Exception as exc:  # malformed client frame
                    await websocket.send_json({"type": "error", "error": f"bad request: {exc}"})
                    continue
                visitor_id = service.visitor_id_for(data)
                async for ev in service.public_chat_events(session, public_key, data, visitor_id):
                    await websocket.send_text(ev.model_dump_json())
                await session.commit()
        except WebSocketDisconnect:
            return
        except Exception as exc:  # surface + close on unexpected failure
            log.warning("public_ws_error", error=str(exc))
            await session.rollback()
            await websocket.close(code=1011)


@router.websocket("/agents/{public_key}/subscribe")
async def public_subscribe_ws(websocket: WebSocket, public_key: str) -> None:
    """Listen-only socket: the widget subscribes to a conversation to receive operator pushes."""
    conversation_id = websocket.query_params.get("conversation_id")
    await websocket.accept()
    if not conversation_id:
        await websocket.close(code=4400)
        return
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        await websocket.close(code=4400)
        return

    # Verify the conversation belongs to the agent for this public key.
    async with SessionFactory() as session:
        agent, _version = await service._resolve_agent(session, public_key)
        conv = await session.get(Conversation, cid)
        if conv is None or conv.agent_id != agent.id:
            await websocket.close(code=4404)
            return

    queue = hub.subscribe(conv_topic(cid))
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        log.warning("public_subscribe_ws_error", error=str(exc))
    finally:
        hub.unsubscribe(conv_topic(cid), queue)
