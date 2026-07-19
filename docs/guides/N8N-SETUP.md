# n8n setup guide

BotForge integrates with a locally-running (or remote) [n8n](https://n8n.io) instance two ways:

1. **BotForge → n8n** — an agent calls an n8n workflow as a **tool** (via the workflow's webhook).
2. **n8n → BotForge** — a workflow calls back into BotForge (signed callback for async tools, or
   the BotForge REST API with an API key) to do real work: create tickets, send email, update a CRM.

This guide covers running n8n and wiring it up. For the ready-made starter workflows and the exact
signed request/response contract, see [`infra/n8n/README.md`](../../infra/n8n/README.md).

## 1. Run n8n

The dev compose file already includes an `n8n` service:

```bash
cd infra && docker compose up -d n8n
# → http://localhost:5678   (basic auth: admin / botforge by default)
```

To point BotForge at an **already-running** n8n instead, just set `N8N_BASE_URL` (below) — the
compose `n8n` service is optional.

## 2. Configure BotForge

In `.env` (see [`ENV.md`](../ENV.md)):

| Variable | Purpose |
|---|---|
| `N8N_BASE_URL` | Where n8n lives (default `http://localhost:5678`; `http://n8n:5678` inside compose). |
| `N8N_API_KEY` | n8n public-API key — lets BotForge **list** your workflows in the Automations UI. Without it, bind a workflow by pasting its webhook URL directly. |
| `N8N_WEBHOOK_SIGNING_SECRET` | HMAC secret BotForge uses to **sign** outbound tool calls (and verify async callbacks). Set it and verify the signature in your workflows for production. |

Create an n8n API key in n8n: **Settings → n8n API → Create an API key**.

## 3. Import a workflow

Import a starter (or your own) and **activate** it so its production webhook registers:

- **UI:** http://localhost:5678 → *Workflows → Import from File* → pick e.g.
  `infra/n8n/botforge-echo.json` → toggle **Active** (top-right).
- **API:** `POST http://localhost:5678/api/v1/workflows` with header `X-N8N-API-KEY`, then
  `POST /api/v1/workflows/{id}/activate`.

A BotForge-callable workflow starts with a **Webhook** node and (for sync tools) ends with a
**Respond to Webhook** node returning JSON.

## 4. Bind it as an agent tool

Dashboard → **Automations** → pick the workflow → **Bind as tool** → choose the agent and mode:

- **sync** — BotForge POSTs to the webhook and feeds the *Respond to Webhook* JSON straight back to
  the model in the same turn.
- **async** — the workflow does long-running work, then POSTs a signed
  `{run_id, output, status}` back to `POST /v1/tools/n8n/callback` to resolve the pending tool run.

No API key? Bind directly by webhook URL (Automations → Bind → paste the URL).

Then enable the agent's **Tools** and chat — when the model decides to call the tool, BotForge
triggers the workflow and uses its response. (This full roundtrip was verified live in Phase 10.)

## 5. n8n → BotForge (the other direction)

To have a workflow act on BotForge, create a BotForge **API key** (Settings → API keys, `bf_`-prefixed)
and call the REST API from an HTTP Request node — e.g. create a conversation, post an inbox message,
or read analytics. See the [API usage guide](API-USAGE.md). BotForge also emits **outbound webhooks**
(`message.created`, `handoff.requested`, …) you can receive with an n8n Webhook node to trigger flows.

## 6. What BotForge sends

Every outbound tool call is a signed POST to the workflow's webhook:

```json
{ "args": { ... }, "mode": "sync|async", "run_id": "<uuid>",
  "conversation_id": "<uuid|null>", "callback_url": "<async only>" }
```

Headers: `X-BotForge-Signature` (HMAC-SHA256 of `"{timestamp}.{body}"` with
`N8N_WEBHOOK_SIGNING_SECRET`) and `X-BotForge-Timestamp`. Verify them for any production workflow.

## Troubleshooting

- **Workflows don't list in Automations** — `N8N_API_KEY` missing/invalid, or `N8N_BASE_URL` wrong.
  Bind by webhook URL as a fallback.
- **Tool call returns an error** — the workflow isn't **Active**, or (sync) has no *Respond to
  Webhook* node. Check the tool run under the agent's Tools tab and the n8n execution log.
- **Callback rejected** — async callback signature/`run_id` mismatch; sign with the same secret.
