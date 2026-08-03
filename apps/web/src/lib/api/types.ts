// Response shapes from the FastAPI backend (docs/04). Hand-written; swap for an
// openapi-generated client later.

export interface ApiUser {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_staff: boolean;
  email_verified: boolean;
  created_at: string;
}

export interface ApiMembership {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  role: string;
  status: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: ApiUser;
}

export interface MeResponse {
  user: ApiUser;
  memberships: ApiMembership[];
}

/** A refresh-token session — one row per signed-in device (`GET /v1/auth/sessions`). */
export interface ApiSession {
  id: string;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  expires_at: string;
  /** True for the session backing the request that listed them. */
  current: boolean;
}

export interface ApiOrg {
  id: string;
  name: string;
  slug: string;
  plan: string;
  avatar_url: string | null;
  /** Detect contact details customers share in chat and file them in the CRM. */
  auto_crm_capture_enabled?: boolean;
  role: string;
  created_at: string;
  updated_at: string;
}

export interface ApiAgent {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  status: "draft" | "published" | "archived";
  public_key: string;
  is_public: boolean;
  current_version_id: string | null;
  draft_version: number;
  created_at: string;
  updated_at: string;
}

export interface ApiVersion {
  id: string;
  version: number;
  is_published: boolean;
  system_prompt: string | null;
  persona: Record<string, unknown>;
  welcome_message: string | null;
  fallback_message: string | null;
  suggested_prompts: string[];
  model_config: Record<string, unknown>;
  rag_config: Record<string, unknown>;
  features: Record<string, unknown>;
  created_at: string;
}

/** A creation-time starting point from `GET /v1/agent-templates`. Static catalog data:
 *  identical for every org, copied into the first draft, never referenced afterwards. */
export interface ApiAgentTemplate {
  id: string;
  label: string;
  icon: string;
  description: string;
  system_prompt: string;
  welcome_message: string;
  suggested_prompts: string[];
  tone: string;
  suggested_next_step: string | null;
}

export interface ApiModelOption {
  id: string;
  label: string;
  context: number | null;
  tools: boolean;
  note: string | null;
  /** False when no per-1K rate is published, so a $0 cost means "not tracked", not "free". */
  pricing_known: boolean;
}

/** How the server resolved this provider's key — see `resolve_credential()`. */
export type ApiKeySource = "org" | "env" | "not_required" | "none";

export interface ApiProviderInfo {
  name: string;
  label: string;
  free: boolean;
  requires_key: boolean;
  /** Model ids only. Prefer `available_models` for anything user-facing. */
  models: string[];
  available_models: ApiModelOption[];
  /** True when this org can actually run the provider today. */
  configured: boolean;
  key_source: ApiKeySource;
  masked_key: string | null;
  credential_id: string | null;
  base_url: string | null;
  base_url_required: boolean;
  api_key_url: string | null;
  key_hint: string | null;
  description: string | null;
}

export interface ApiProviderModels {
  provider: string;
  /** `catalog` means discovery was unavailable and these are the static defaults. */
  source: "live" | "catalog";
  models: ApiModelOption[];
  error: string | null;
}

export interface ApiCredential {
  id: string;
  provider: string;
  label: string | null;
  masked_key: string;
  base_url: string | null;
  is_default: boolean;
  created_at: string;
}

export interface ApiKnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  embedding_provider: string;
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export type ApiDocStatus = "queued" | "processing" | "ready" | "failed";

export interface ApiDocument {
  id: string;
  knowledge_base_id: string;
  source_type: "file" | "url" | "text";
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  source_url: string | null;
  status: ApiDocStatus;
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface ApiChunk {
  id: string;
  ordinal: number;
  content: string;
  token_count: number;
  metadata: Record<string, unknown>;
}

export interface ApiCitation {
  chunk_id: string;
  document_id: string;
  knowledge_base_id: string;
  ordinal: number;
  content: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface ApiSearchResponse {
  query: string;
  citations: ApiCitation[];
}
