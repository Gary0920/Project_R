import { apiRequest, type ApiClientOptions } from "../../shared/api/client";
import type { CompanyPromptResponse } from "../../shared/api/types";

export function listCompanyPrompts(options: ApiClientOptions) {
  return apiRequest<CompanyPromptResponse[]>(options, "/prompts/company");
}
