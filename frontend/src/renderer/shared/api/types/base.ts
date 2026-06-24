// ==========================================================================
// Shared / infrastructure types
// ==========================================================================

export type ApiErrorPayload = {
  detail?: string;
};

export type HealthResponse = {
  status: string;
};

export type LLMProviderStatusResponse = {
  profile?: string | null;
  provider: string;
  label?: string;
  description?: string;
  default: boolean;
  configured: boolean;
  key_count: number;
  model: string;
  base_url: string;
  api_version: string | null;
  reasoning_effort?: string | null;
  supports_vision?: boolean;
};

export type LLMHealthResponse = {
  profile?: string | null;
  label?: string | null;
  description?: string | null;
  provider: string;
  configured: boolean;
  key_count: number;
  model: string;
  base_url: string;
  api_version: string | null;
  reasoning_effort?: string | null;
  supports_vision?: boolean;
  providers: LLMProviderStatusResponse[];
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type LoginResponse = {
  token: string;
  user_id: number;
  username: string;
  role: "admin" | "employee" | string;
  nickname: string;
  avatar: string;
  work_group: string;
  last_login_at: string | null;
};

export type CurrentUserResponse = Omit<LoginResponse, "token">;
