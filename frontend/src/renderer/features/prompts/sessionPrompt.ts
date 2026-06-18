import type { SendChatMessageResponse } from "../../shared/api/types";
import type { PromptSource } from "./components/PromptPanel";

export const PROMPT_SELECTION_KEY = "project_r_session_prompt_selection";

const SETTINGS_PREFERENCES_KEY = "project-r:settings-preferences";
const AGENT_MODE_PROMPT = (
  "当前用户已切换到 Agent 模式。请更积极地承接执行型任务："
  + "当请求涉及文件生成、套模板、业务 Skill、多步骤流程、项目资料核对或可下载输出时，"
  + "优先推进执行、追问必要字段，并避免只给泛泛说明。"
);
const AGENT_SUGGESTION_KEYWORDS = [
  "excel",
  "xlsx",
  "ppt",
  "pptx",
  "模板",
  "套用",
  "skill",
  "流程",
  "审批",
  "审计",
  "项目",
  "资料",
  "文件夹",
  "读取",
  "核对",
  "批量",
  "多步骤",
  "生成表格",
  "项目资料",
];

export function readPromptSelectionMap() {
  try {
    return JSON.parse(localStorage.getItem(PROMPT_SELECTION_KEY) ?? "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

export function readWebSearchPreference() {
  return false;
}

export function writeWebSearchPreference(_enabled: boolean) {
  try {
    const preferences = JSON.parse(localStorage.getItem(SETTINGS_PREFERENCES_KEY) ?? "{}") as Record<string, unknown>;
    delete preferences.webSearchEnabled;
    localStorage.setItem(SETTINGS_PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {
    // Invalid preference JSON should not make a paid search feature default-on.
  }
}

export function makePromptId(source: PromptSource, id: string) {
  return `${source}:${id}`;
}

export function composeSystemPrompt(basePrompt: string, mode: "chat" | "agent") {
  if (mode !== "agent") return basePrompt;
  return [basePrompt, AGENT_MODE_PROMPT].filter(Boolean).join("\n\n");
}

export function shouldSuggestAgentMode(
  request: string,
  response: SendChatMessageResponse,
  mode: "chat" | "agent",
) {
  if (mode === "agent") return null;
  if (response.generated_file) return null;
  if (response.skill_run) {
    return "已识别为业务执行任务，Agent 模式更适合补参、调用 Skill 并跟踪输出。";
  }
  const normalized = request.trim().toLowerCase();
  const asksForComplexOutput = AGENT_SUGGESTION_KEYWORDS.some((keyword) => normalized.includes(keyword));
  if (asksForComplexOutput) {
    return "这个请求可能需要读取资料、套模板或执行多步骤流程，建议交给 Agent 模式承接。";
  }
  if (response.intent === "document_generation" && !response.generated_file) {
    return "这个文件生成请求没有返回下载文件，建议切换 Agent 模式继续处理。";
  }
  return null;
}
