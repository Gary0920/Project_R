import { apiRequest, type ApiClientOptions } from "./client";
import type { LLMHealthResponse } from "./types";

export function getLLMHealth(options: ApiClientOptions) {
  return apiRequest<LLMHealthResponse>(options, "/health/llm");
}
