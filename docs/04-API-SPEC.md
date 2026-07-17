# 04 — REST API Specification

Base URL: `/v1`. JSON everywhere. Auth via `Authorization: Bearer <access_token>` (dashboard)
or `Authorization: Bearer <api_key>` (programmatic, prefix `bf_`). All list endpoints:
cursor or page/limit pagination, `?limit=&cursor=` returning `{data:[], next_cursor}`.
FastAPI auto-generates OpenAPI at `/openapi.json`; the frontend generates its typed client
from it. Error model per `02 §8`.

## Conventions
- Timestamps ISO-8601 UTC. IDs are UUID strings.
- Org context: resolved from token; org-scoped routes are `/v1/orgs/{org_id}/...` OR the
  current org is taken from an `X-Org-Id` header validated against membership. Pick one
  (recommend `X-Org-Id` header + membership check) and be consistent.
- Standard responses include `id, created_at, updated_at`.
- Write endpoints validate RBAC per `02 §6`.

## Auth  `/v1/auth`
- `POST /signup` `{email, password, full_name}` → user + tokens.
- `POST /login` `{email, password}` → `{access_token, refresh_token, user}`.
- `POST /refresh` `{refresh_token}` → new pair (rotates).
- `POST /logout` → revoke current refresh/session.
- `GET  /me` → current user + memberships.
- `POST /verify-email` `{token}` / `POST /verify-email/resend`.
- `POST /password/forgot` `{email}` / `POST /password/reset` `{token, password}`.
- `POST /magic-link` `{email}` / `POST /magic-link/verify` `{token}`.
- OAuth: `GET /oauth/{provider}/authorize` → redirect URL; `GET /oauth/{provider}/callback`.
- `GET /sessions` / `DELETE /sessions/{id}`.

## Organizations  `/v1/orgs`
- `POST /` create org `{name}`.
- `GET /` list my orgs.  `GET /{id}` / `PATCH /{id}` / `DELETE /{id}`.
- Members: `GET /{id}/members`, `PATCH /{id}/members/{userId}` (role), `DELETE /{id}/members/{userId}`.
- Invites: `POST /{id}/invitations` `{email, role}`, `GET /{id}/invitations`,
  `POST /invitations/{token}/accept`, `DELETE /{id}/invitations/{invId}`.
- `POST /{id}/transfer-ownership` `{userId}`.

## Agents  `/v1/agents`
- `POST /` create `{name, description}` → agent (draft v1).
- `GET /` list.  `GET /{id}` / `PATCH /{id}` / `DELETE /{id}` / `POST /{id}/duplicate`.
- Versions: `GET /{id}/versions`, `POST /{id}/versions` (new draft),
  `PATCH /{id}/versions/{v}` (persona, model_config, rag_config, features, prompts),
  `POST /{id}/versions/{v}/publish`, `POST /{id}/rollback` `{version}`.
- Playground: `POST /{id}/playground/chat` (streams; uses draft version).
- Provider creds: `GET/POST/DELETE /{id}/credentials` (BYO keys, per agent).

## Provider credentials (org-level)  `/v1/credentials`
- `GET /` list (keys masked).  `POST /` `{provider, label, api_key, base_url?, is_default?}`.
- `PATCH /{id}` / `DELETE /{id}`.  `POST /{id}/test` → validates key against provider.
- `GET /providers` → list supported providers + their available models (Groq/Gemini/Ollama
  discovered dynamically where possible).

## Knowledge base  `/v1/knowledge`
- `POST /` create KB `{name, embedding_provider, embedding_model, chunk_size, chunk_overlap}`.
- `GET /` / `GET /{id}` / `PATCH /{id}` / `DELETE /{id}`.
- Documents: `POST /{id}/documents` (multipart file OR `{source_type:url|text, ...}`),
  `GET /{id}/documents`, `GET /documents/{docId}` (status/progress),
  `POST /documents/{docId}/reindex`, `DELETE /documents/{docId}`,
  `GET /documents/{docId}/chunks`.
- Retrieval test: `POST /{id}/search` `{query, top_k}` → chunks + scores.

## Chat  `/v1/agents/{id}/chat`  (dashboard + API)
- `POST /agents/{id}/chat` `{conversation_id?, message, stream?}` →
  SSE stream of `{type: token|tool_call|tool_result|citation|done, ...}` or JSON if not streamed.
- WebSocket `WS /v1/agents/{id}/chat/ws` — bidirectional streaming.
- Conversations: `GET /v1/conversations?agent_id=`, `GET /v1/conversations/{cid}`,
  `GET /v1/conversations/{cid}/messages`, `PATCH /v1/conversations/{cid}` (title/status),
  `DELETE /v1/conversations/{cid}`.

## Public chat (widget & channels)  `/v1/public`
- `GET /public/agents/{public_key}/config` → widget theme, welcome, suggested prompts.
- `POST /public/agents/{public_key}/chat` (rate-limited, no dashboard auth; optional
  visitor token) → same streaming contract.
- `WS /public/agents/{public_key}/ws`.

## Tools  `/v1/tools`
- `GET /builtin` → available built-in tools.
- `GET /` / `POST /` `{name, type, description, config, input_schema, agent_id?}`.
- `GET /{id}` / `PATCH /{id}` / `DELETE /{id}` / `POST /{id}/test` `{input}`.
- Runs: `GET /runs?conversation_id=` → tool_runs log.
- n8n: `GET /n8n/workflows` (proxy list from n8n), `POST /n8n/bind` `{workflow_id, name,
  mode}` → creates an n8n tool.

## Channels  `/v1/channels`
- `GET /` / `POST /` `{agent_id, type, name, config}` / `GET /{id}` / `PATCH /{id}` / `DELETE /{id}`.
- `POST /{id}/enable` / `POST /{id}/disable`.
- Widget snippet: `GET /{id}/embed` → `<script>` snippet + instructions.
- Inbound webhooks (public, signature-verified):
  `POST /channels/telegram/{channelId}/webhook`,
  `POST /channels/whatsapp/{channelId}/webhook` (+ `GET` for Meta verify challenge),
  `POST /channels/slack/{channelId}/events`,
  `POST /channels/discord/{channelId}/interactions`.

## Inbox / handoff  `/v1/inbox`
- `GET /conversations?status=` (active/handoff/closed), `GET /conversations/{cid}`.
- `POST /conversations/{cid}/takeover`, `POST /conversations/{cid}/handback`,
  `POST /conversations/{cid}/messages` (operator reply),
  `POST /conversations/{cid}/assign` `{userId}`, `POST /conversations/{cid}/close`,
  `POST /conversations/{cid}/notes`, `POST /conversations/{cid}/tags`.

## Analytics  `/v1/analytics`
- `GET /overview?agent_id=&from=&to=` → conversations, messages, users, resolution/handoff rate.
- `GET /usage?agent_id=&from=&to=&group_by=day|provider|model` → tokens + cost.
- `GET /latency`, `GET /top-questions`, `GET /unanswered`.
- `GET /export?type=usage|conversations&from=&to=` → CSV.

## API keys  `/v1/apikeys`
- `GET /` / `POST /` `{name, scopes, expires_at?}` → returns full key **once**.
- `POST /{id}/revoke` / `DELETE /{id}`.

## Webhooks (outbound)  `/v1/webhooks`
- `GET /` / `POST /` `{url, events}` / `PATCH /{id}` / `DELETE /{id}` / `POST /{id}/test`.
- `GET /{id}/deliveries` → delivery log.
- Event catalog: `message.created`, `conversation.created`, `handoff.requested`,
  `handoff.resolved`, `document.ready`, `document.failed`, `tool.run`, `usage.threshold`.

## Admin (platform staff, `is_staff`)  `/v1/admin`
- `GET /orgs`, `GET /users`, `GET /usage`, `GET /health`, feature flags CRUD.

## Billing (optional)  `/v1/billing`
- `GET /subscription`, `POST /checkout`, `POST /portal`, `POST /webhook` (Stripe).

## System
- `GET /healthz`, `GET /readyz`, `GET /metrics`, `GET /version`.

## Streaming event contract (SSE/WS)
Each event: `{ "type": "...", ... }`
- `token` `{delta}` — a text chunk.
- `tool_call` `{tool, input, run_id}` — model requested a tool.
- `tool_result` `{run_id, output, status}`.
- `citation` `{document_id, chunk_id, snippet, score}`.
- `message` `{message_id}` — assistant message persisted.
- `error` `{code, message}`.
- `done` `{usage: {tokens_prompt, tokens_completion, cost_micros}, provider, model}`.

## Rate limiting
Public chat + auth endpoints: Redis token bucket per IP + per public_key/api_key. Return
`429` with `Retry-After`. Limits configurable via env.
