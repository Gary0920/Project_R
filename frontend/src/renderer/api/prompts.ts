import { apiRequest, type ApiClientOptions } from "./client";
import type { CompanyPromptResponse } from "./types";

export function listCompanyPrompts(options: ApiClientOptions) {
  return apiRequest<CompanyPromptResponse[]>(options, "/prompts/company");
}
