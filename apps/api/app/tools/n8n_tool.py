"""Execution of n8n-bound tools (docs/07 §1).

Config shape (Tool.config):
    {"workflow_id": "...", "workflow_name": "...", "webhook_url": "...", "mode": "sync"|"async"}

- **sync**: POST the args to the workflow's webhook and feed n8n's "Respond to Webhook" JSON
  straight back to the model.
- **async**: POST args + a `callback_url` carrying this tool_run's id; return an "accepted"
  result immediately. n8n later calls the callback, which resolves the pending tool_run.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.errors import AppError
from app.integrations.n8n_client import get_client
from app.tools.base import ToolContext, ToolResult


async def execute_n8n_tool(config: dict[str, Any], args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    webhook_url = str(config.get("webhook_url", "")).strip()
    mode = str(config.get("mode", "sync")).lower()
    if not webhook_url:
        return ToolResult(output={}, status="error", error="n8n tool has no webhook_url configured")

    payload: dict[str, Any] = {
        "args": args,
        "mode": mode,
        "run_id": str(ctx.run_id) if ctx.run_id else None,
        "conversation_id": str(ctx.conversation_id) if ctx.conversation_id else None,
    }
    if mode == "async":
        payload["callback_url"] = f"{settings.api_base_url.rstrip('/')}/v1/tools/n8n/callback"

    client = get_client()
    try:
        status_code, data = await client.trigger_webhook(webhook_url, payload)
    except AppError as exc:
        return ToolResult(output={}, status="error", error=exc.message)

    if mode == "async":
        return ToolResult(
            output={
                "status": "accepted",
                "run_id": payload["run_id"],
                "note": "n8n is processing asynchronously; the result will be recorded via callback.",
            },
            status="pending",
        )

    if status_code >= 400:
        return ToolResult(output={"response": data}, status="error", error=f"n8n returned {status_code}")
    return ToolResult(output={"response": data}, status="success")
