import { apiRequest, type ApiClientOptions } from "../../shared/api/client";
import type { SkillMatchResponse, SkillResponse, SkillRunResponse } from "../../shared/api/types";

export function listSkills(options: ApiClientOptions) {
  return apiRequest<SkillResponse[]>(options, "/skills");
}

export function matchSkill(options: ApiClientOptions, text: string) {
  return apiRequest<SkillMatchResponse>(options, "/skills/match", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function startSkillRun(
  options: ApiClientOptions,
  data: { skill_name: string; session_id?: number | null; inputs?: Record<string, unknown> },
) {
  return apiRequest<SkillRunResponse>(options, "/skills/runs", {
    method: "POST",
    body: JSON.stringify({
      skill_name: data.skill_name,
      session_id: data.session_id ?? null,
      inputs: data.inputs ?? {},
    }),
  });
}

export function getSkillRun(options: ApiClientOptions, runId: number) {
  return apiRequest<SkillRunResponse>(options, `/skills/runs/${runId}`);
}

export function submitSkillInput(options: ApiClientOptions, runId: number, inputs: Record<string, unknown>) {
  return apiRequest<SkillRunResponse>(options, `/skills/runs/${runId}/inputs`, {
    method: "POST",
    body: JSON.stringify({ inputs }),
  });
}
