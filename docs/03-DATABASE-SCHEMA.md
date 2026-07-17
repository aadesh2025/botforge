# 03 — Database Schema (PostgreSQL 16 + pgvector)

Conventions: `id` = UUID (v7 preferred) primary key. `created_at`, `updated_at` timestamptz
on every table (UTC). Soft-delete via `deleted_at` on user-facing resources. Every
tenant-owned table has `organization_id` FK with an index. Money/tokens as integers.
Enums implemented as Postgres enum types or `varchar` + check constraints. Use Alembic
migrations for every change. Enable extensions: `pgcrypto`, `vector`.

> Below is the logical schema. Claude Code implements it as SQLAlchemy 2.0 models +
> Alembic migrations. Adjust column types sensibly; keep the relationships.

## Identity & tenancy

### users
`id, email (unique, citext), email_verified_at, password_hash (nullable for oauth-only),
full_name, avatar_url, is_staff (bool, platform admin), is_active, last_login_at,
created_at, updated_at, deleted_at`

### oauth_accounts
`id, user_id→users, provider (google|github), provider_account_id, access_token_enc,
refresh_token_enc, expires_at, created_at` — unique(provider, provider_account_id)

### magic_link_tokens
`id, user_id→users, token_hash, expires_at, used_at, created_at`

### password_reset_tokens
`id, user_id→users, token_hash, expires_at, used_at, created_at`

### sessions (refresh tokens)
`id, user_id→users, refresh_token_hash, user_agent, ip, expires_at, revoked_at, created_at`

### organizations
`id, name, slug (unique), avatar_url, plan (free|pro|enterprise), settings (jsonb),
created_by→users, created_at, updated_at, deleted_at`

### memberships
`id, organization_id→organizations, user_id→users, role (owner|admin|editor|viewer|operator),
status (active|invited|removed), created_at, updated_at` — unique(organization_id, user_id)

### invitations
`id, organization_id, email, role, token_hash, invited_by→users, expires_at, accepted_at,
created_at`

## Agents & configuration

### agents
`id, organization_id, name, slug, avatar_url, description, status (draft|published|archived),
public_key (unique, for widget), is_public (bool), current_version_id→agent_versions,
created_by, created_at, updated_at, deleted_at`

### agent_versions
`id, agent_id→agents, version (int), is_published (bool),
system_prompt (text), persona (jsonb: {character, role, tone, guardrails[]}),
welcome_message, fallback_message, suggested_prompts (jsonb[]),
model_config (jsonb: {provider, model, temperature, top_p, max_tokens,
  frequency_penalty, presence_penalty, stop[]}),
rag_config (jsonb: {enabled, knowledge_base_ids[], top_k, score_threshold, hybrid}),
features (jsonb: {tools_enabled, memory_enabled, handoff_enabled}),
created_by, created_at` — unique(agent_id, version)

### provider_credentials  (BYO API keys, per org or per agent)
`id, organization_id, agent_id (nullable), provider (groq|gemini|ollama|openrouter|openai|
anthropic|custom), label, api_key_enc, base_url (for custom/ollama/openrouter),
extra (jsonb), is_default (bool), created_by, created_at, updated_at`

## Knowledge base & RAG

### knowledge_bases
`id, organization_id, name, description, embedding_provider, embedding_model,
chunk_size (int), chunk_overlap (int), created_by, created_at, updated_at, deleted_at`

### documents
`id, knowledge_base_id→knowledge_bases, organization_id, source_type (file|url|text),
filename, mime_type, size_bytes, source_url, status (queued|processing|ready|failed),
error_message, chunk_count (int), storage_path, created_by, created_at, updated_at`

### chunks
`id, document_id→documents, knowledge_base_id, organization_id, ordinal (int),
content (text), token_count (int), metadata (jsonb: {page, heading, ...}),
embedding vector(768)  -- dimension = embedding model; make configurable,
created_at`
Indexes: ivfflat/hnsw on `embedding` (cosine); btree on (knowledge_base_id); GIN on
`to_tsvector(content)` for hybrid keyword search.

## Conversations & messages

### conversations
`id, organization_id, agent_id→agents, channel (web|widget|api|telegram|whatsapp|slack|
discord), channel_user_id, external_id, status (active|handoff|closed),
assigned_to→users (nullable), title, metadata (jsonb), memory_summary (text),
last_message_at, created_at, updated_at`

### messages
`id, conversation_id→conversations, organization_id, role (user|assistant|system|tool),
content (text), tool_calls (jsonb), tool_call_id, citations (jsonb[]: {document_id,
chunk_id, score, snippet}), provider, model, tokens_prompt (int), tokens_completion (int),
cost_micros (int), latency_ms (int), error (text), created_at`

## Tools & automations

### tools
`id, organization_id, agent_id (nullable = org-shared), name, type (builtin|http|n8n),
description, enabled (bool),
config (jsonb: for http {method,url,headers,body_schema,auth}; for n8n {workflow_id,
webhook_url, mode:sync|async}; for builtin {key}),
input_schema (jsonb), created_by, created_at, updated_at`

### tool_runs
`id, organization_id, tool_id→tools, conversation_id, message_id, input (jsonb),
output (jsonb), status (success|error|timeout), latency_ms, error, created_at`

## Channels

### channels
`id, organization_id, agent_id→agents, type (widget|telegram|whatsapp|slack|discord|api),
name, enabled (bool),
config (jsonb: widget {theme,colors,position,launcher,branding}; telegram {bot_token_enc};
whatsapp {phone_id, token_enc, verify_token}; slack/discord {tokens_enc, signing_secret}),
webhook_secret, created_by, created_at, updated_at` — index(organization_id, type)

## Inbox / handoff

### handoffs
`id, organization_id, conversation_id, requested_by (bot|user), reason, status
(open|assigned|resolved), assigned_to→users, notes (jsonb[]), tags (text[]),
created_at, resolved_at`

## Platform: keys, webhooks, audit, usage, billing

### api_keys
`id, organization_id, name, key_prefix, key_hash, scopes (text[]), last_used_at,
expires_at, revoked_at, created_by, created_at`

### webhook_endpoints
`id, organization_id, url, events (text[]), secret, enabled, created_at, updated_at`

### webhook_deliveries
`id, webhook_endpoint_id, event, payload (jsonb), status (pending|success|failed),
attempts (int), response_status, next_retry_at, created_at`

### audit_logs
`id, organization_id, actor_user_id, action (string), target_type, target_id,
metadata (jsonb), ip, created_at`

### usage_records  (metering)
`id, organization_id, agent_id, date (date), provider, model,
tokens_prompt (bigint), tokens_completion (bigint), requests (int), cost_micros (bigint)`
— unique(organization_id, agent_id, date, provider, model)

### quotas
`id, organization_id, period (month), token_limit (bigint), tokens_used (bigint),
request_limit (int), requests_used (int), resets_at`

### subscriptions  (billing, optional)
`id, organization_id, stripe_customer_id, stripe_subscription_id, plan, status,
current_period_end, created_at, updated_at`

## Relationship summary

- user 1—* memberships *—1 organization (many-to-many via memberships).
- organization 1—* agents 1—* agent_versions.
- organization 1—* knowledge_bases 1—* documents 1—* chunks (with vector embeddings).
- agent_version.rag_config references knowledge_base ids.
- organization 1—* conversations 1—* messages; conversation *—1 agent.
- agent/organization 1—* tools 1—* tool_runs.
- organization 1—* channels *—1 agent.
- conversation 1—* handoffs.
- organization 1—* {api_keys, webhook_endpoints, audit_logs, usage_records, quotas}.

## Indexing checklist (create in migrations)

- FK columns, `organization_id` on every tenant table.
- `chunks.embedding` HNSW/IVFFlat cosine; `chunks` GIN tsvector for hybrid.
- `conversations(agent_id, last_message_at)`, `messages(conversation_id, created_at)`.
- `usage_records(organization_id, date)`, `agents(public_key)`, `channels(type, enabled)`.
- Unique constraints as noted above.

## Seed data (dev)

Create a seed script: one org, one owner user (from `.env`), one demo agent (Groq,
temperature 0.7) with a small knowledge base of 2–3 sample docs, one sample HTTP tool, and
one widget channel — so `docker compose up` yields a working demo immediately.
