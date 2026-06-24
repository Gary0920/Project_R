import type { GeneratedFileResponse } from "./chat";

export type SkillResponse = {
  name: string;
  display_name: string;
  description: string;
  category: string;
  priority: string;
  trigger: string[];
  inputs: Array<Record<string, unknown>>;
  outputs: Array<Record<string, unknown>>;
  references: string[];
  execution: Record<string, unknown>;
  governance: Record<string, unknown>;
  path: string;
};

export type SkillMatchResponse = {
  skill: SkillResponse | null;
  confidence: number;
  reason: string;
};

export type SkillRunResponse = {
  id: number;
  skill_name: string;
  skill: SkillResponse | null;
  user_id: number;
  session_id: number | null;
  status: string;
  inputs: Record<string, unknown>;
  missing_inputs: Array<Record<string, unknown>>;
  dispatch: Record<string, unknown> | null;
  generated_file: GeneratedFileResponse | null;
  created_at: string;
  updated_at: string;
};
