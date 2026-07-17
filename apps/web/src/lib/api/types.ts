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
