# Starter n8n workflows

Importable workflows that BotForge agents can call as **n8n tools** (docs/07 §1).

| File | Webhook path | Mode | What it does |
|---|---|---|---|
| `botforge-echo.json` | `/webhook/botforge-echo` | sync | Echoes the tool arguments back — smoke test for a bound tool. |
| `create-support-ticket.json` | `/webhook/botforge-create-ticket` | sync | Generates a ticket id + status and returns it (a "Respond to Webhook" example). |

## How BotForge calls them

When an agent invokes a bound n8n tool, BotForge `POST`s to the workflow's webhook URL with:

```json
{
  "args": { ...the tool arguments the model produced... },
  "mode": "sync" | "async",
  "run_id": "<tool_run uuid>",
  "conversation_id": "<uuid|null>",
  "callback_url": "http://localhost:8000/v1/tools/n8n/callback"   // async only
}
```

Every request is signed: headers `X-BotForge-Signature` (HMAC-SHA256 of `"{timestamp}.{body}"`
using `N8N_WEBHOOK_SIGNING_SECRET`) and `X-BotForge-Timestamp`. Verify these in n8n for
production workflows.

- **Sync** workflows must end in a **Respond to Webhook** node returning JSON — that JSON is fed
  straight back to the model.
- **Async** workflows do their work, then `POST` back to `callback_url` with a signed body
  `{ "run_id", "output", "status" }` to resolve the pending tool run.

## Import

**Via the n8n UI:** open http://localhost:5678 (basic auth `admin` / `botforge`) →
*Workflows* → *Import from File* → pick a JSON here → **Activate** the workflow (top-right
toggle) so the production webhook registers.

**Via the public API:**

```bash
KEY=$N8N_API_KEY
curl -s -H "X-N8N-API-KEY: $KEY" -H "Content-Type: application/json" \
  -X POST http://localhost:5678/api/v1/workflows \
  --data-binary @infra/n8n/botforge-echo.json
# then activate it:  POST /api/v1/workflows/{id}/activate
```

## Bind in BotForge

Dashboard → **Automations** → pick the workflow → **Bind as tool** (choose the agent + mode).
Then enable the agent's tools and chat — the agent can call the workflow and use its response.
