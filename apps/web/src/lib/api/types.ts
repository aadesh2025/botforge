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

export interface ApiOrg {
  id: string;
  name: string;
  slug: string;
  plan: string;
  avatar_url: string | null;
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

export interface ApiProviderInfo {
  name: string;
  label: string;
  free: boolean;
  requires_key: boolean;
  models: string[];
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
