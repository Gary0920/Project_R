import type { ChatContextTraceResponse } from "../../shared/api/types";

export const DEFAULT_PROMPT_ID = "builtin:builtin-project-r";

export function isDefaultPromptId(promptId: string | null | undefined) {
  return promptId === DEFAULT_PROMPT_ID;
}

export function hasNonDefaultSessionPrompt(prompt: ChatContextTraceResponse["prompt"]) {
  return Boolean(prompt?.selected_prompt_id && !isDefaultPromptId(prompt.selected_prompt_id));
}

function hasGBrainThinkIssues(gbrainThink: ChatContextTraceResponse["gbrain_think"]) {
  return Boolean(
    gbrainThink?.gap_count ||
    gbrainThink?.conflict_count ||
    gbrainThink?.warning_count ||
    gbrainThink?.gaps?.length ||
    gbrainThink?.conflicts?.length ||
    gbrainThink?.warnings?.length,
  );
}

function getWebSearchTrace(contextTrace: ChatContextTraceResponse) {
  return contextTrace.web_search as {
    query?: string;
    result_count?: number;
    provider?: string;
    fallback_used?: boolean;
  } | undefined;
}

export function hasWebSearchTraceResults(contextTrace: ChatContextTraceResponse) {
  const webSearch = getWebSearchTrace(contextTrace);
  return typeof webSearch?.result_count === "number" && webSearch.result_count > 0;
}

function shouldShowKnowledgeTrace(contextTrace: ChatContextTraceResponse, messageSourceCount: number) {
  if (messageSourceCount > 0) return false;
  return Boolean((contextTrace.knowledge?.source_count ?? 0) > 0 || contextTrace.knowledge?.sources?.length);
}

function shouldShowWebSearchSection(contextTrace: ChatContextTraceResponse, messageSourceCount: number) {
  if (!hasWebSearchTraceResults(contextTrace)) return false;
  return messageSourceCount === 0;
}

export function shouldShowContextTraceCard(
  contextTrace: ChatContextTraceResponse | null | undefined,
  messageSourceCount = 0,
) {
  if (!contextTrace) return false;
  return Boolean(
    contextTrace.attachments?.length ||
    shouldShowKnowledgeTrace(contextTrace, messageSourceCount) ||
    hasNonDefaultSessionPrompt(contextTrace.prompt) ||
    contextTrace.skill?.skill_name ||
    hasGBrainThinkIssues(contextTrace.gbrain_think) ||
    shouldShowWebSearchSection(contextTrace, messageSourceCount),
  );
}

export function buildWebSearchSummary(contextTrace: ChatContextTraceResponse) {
  const webSearch = getWebSearchTrace(contextTrace);
  if (!webSearch || !webSearch.result_count) return null;
  const providerLabel = webSearch.fallback_used ? `${webSearch.provider ?? "fallback"}` : (webSearch.provider ?? "联网搜索");
  return {
    query: webSearch.query?.trim() || "本轮问题",
    resultCount: webSearch.result_count,
    providerLabel,
  };
}
