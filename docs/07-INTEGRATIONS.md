# 07 — Integrations (n8n, Channels, Widget, Webhooks, Connectors)

## 1. n8n (local Docker) — first-class automation partner

### Runtime
- n8n runs in Docker at `N8N_BASE_URL` (default `http://n8n:5678` inside compose,
  `http://localhost:5678` from host). Add it to `infra/docker-compose.yml`.
- Auth to n8n's REST API via `N8N_API_KEY` (n8n public API) for listing/reading workflows.
- Assume the user may already run n8n; support pointing at an external instance via env.

### Two-way integration
**BotForge → n8n (agent triggers automations):**
- Bind an n8n workflow (that starts with a **Webhook** node) as a BotForge **n8n tool**.
- When the agent calls the tool, `integrations/n8n_client` POSTs the tool arguments to the
  workflow's webhook URL. Sign the request (HMAC header `X-BotForge-Signature`).
- **Sync mode**: n8n's "Respond to Webhook" node returns JSON → fed back to the model.
- **Async mode**: n8n does long work, then calls back BotForge's callback endpoint with the
  `run_id`; runtime resolves the pending tool call.
- Discovery: `GET /v1/tools/n8n/workflows` proxies n8n's API to list workflows so the user
  can pick one in the UI, then `POST /v1/tools/n8n/bind`.

**n8n → BotForge (workflows use BotForge):**
- n8n calls BotForge's REST API using an org **API key** (`bf_...`) — e.g., send a message
  to a conversation, fetch analytics, trigger an agent.
- BotForge emits **outbound webhooks** (see §4) that n8n workflows subscribe to via Webhook
  nodes (e.g., on `handoff.requested`, create a ticket).

### n8n client responsibilities (`integrations/n8n_client.py`)
- `list_workflows()`, `get_workflow(id)`, `trigger_webhook(url, payload, signed=True)`,
  `verify_callback(signature, body)`. Timeouts, retries with backoff, structured logging.

### Provide starter n8n workflows (export JSON in `infra/n8n/`)
- "Create support ticket" (webhook → HTTP/DB node → respond).
- "Send email on handoff" (BotForge webhook → email node).
- Document how to import them in `09-DEPLOYMENT.md`.

## 2. Channels

Each channel = an inbound webhook (receive user messages) + an outbound sender (deliver bot
replies), mapped to a `channels` row and its agent. All inbound endpoints verify signatures.

### Web widget (default, always available)
See §3.

### Telegram
- Config: `bot_token`. On enable, set the bot's webhook to
  `/v1/channels/telegram/{channelId}/webhook` (with a secret token).
- Inbound: parse update → resolve/create conversation keyed by Telegram chat id → run chat →
  send reply via `sendMessage`. Support typing action, basic markdown.

### WhatsApp (Meta Cloud API; Twilio as alt)
- Config: `phone_number_id`, `access_token`, `verify_token`, `app_secret`.
- `GET` webhook: respond to Meta's verification challenge.
- `POST` webhook: verify `X-Hub-Signature-256`, parse message → chat → reply via Graph API
  `messages` endpoint. Handle 24-hour window / templates note in docs.

### Slack
- Config: bot token, signing secret. Verify Slack signature. Handle `event_callback`
  (app_mention / message.im) → chat → `chat.postMessage`. Support Slack markdown.

### Discord
- Config: bot token / application public key. Verify Ed25519 signature on interactions →
  chat → respond. (Gateway/bot mode optional; start with interactions/webhook.)

### Public REST channel
- Any external system posts to `/v1/public/agents/{public_key}/chat` with rate limiting.

### Channel abstraction
Implement a `Channel` interface: `verify(request)`, `parse_inbound(request) -> InboundMsg`,
`send(conversation, text, attachments)`. Register per type. Keeps `chat.service` channel-agnostic.

## 3. Embeddable web widget (`packages/widget`)

### Embed
```html
<script src="https://YOUR_HOST/widget.js" data-agent="PUBLIC_KEY" defer></script>
```
- Loads config from `GET /v1/public/agents/{public_key}/config` (theme, colors, position,
  launcher, welcome message, suggested prompts, branding).
- Renders a launcher bubble + panel in a Shadow DOM (style isolation).
- Chats over `WS /v1/public/agents/{public_key}/ws` (fallback SSE), streaming tokens.

### Features (FR-G2)
Typing indicator, quick replies/suggested prompts, markdown rendering (sanitized), file
upload, message history in session, custom colors/logo/position (bottom-right/left),
"powered by" toggle, mobile responsive, keyboard accessible, RTL support.

### Build
Bundled with a small toolchain (esbuild/vite) to a single minified `widget.js` + `widget.css`,
served by the web app (or a CDN path). No heavy framework in the bundle; keep it lightweight.

### Widget SDK (JS API)
Expose `window.BotForge = { open(), close(), sendMessage(text), on(event, cb),
setUser({id, name, email, metadata}) }` so host pages can control it and pass visitor identity.

## 4. Outbound webhooks (BotForge → external / n8n)

- Configurable endpoints (`webhook_endpoints`) subscribe to events.
- Delivery: enqueue → POST signed payload (`X-BotForge-Signature` = HMAC-SHA256 of body with
  endpoint secret, plus timestamp) → retry with exponential backoff, record in
  `webhook_deliveries`.
- Event catalog: `message.created`, `conversation.created`, `conversation.closed`,
  `handoff.requested`, `handoff.resolved`, `document.ready`, `document.failed`, `tool.run`,
  `usage.threshold`.
- Provide an HMAC verification recipe in docs for consumers.

## 5. Connector suggestions & MCP (forward-looking)

- The HTTP-tool + n8n-tool mechanism already lets agents reach Gmail, Slack, Sheets, Stripe,
  HubSpot, Salesforce, etc. **through n8n nodes** — favor that path over bespoke code.
- Optionally expose an **MCP-compatible** tool bridge so agents can use MCP servers later
  (stretch; note in roadmap).

## 6. Security for all integrations
- Every inbound webhook: signature verification + timestamp/replay protection.
- Every outbound call: HMAC signing, TLS, SSRF guards (block private/link-local/metadata IPs),
  timeouts, size limits.
- Channel tokens and n8n keys stored encrypted; masked in API responses.
