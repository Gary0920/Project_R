import type { TransformTextResponse } from "../../shared/api/types";

export type TextTransformAction = "rewrite" | "translate" | "summarize" | "expand";

export type TextTransformResult = {
  id: string;
  sourceMessageId: number;
  action: TextTransformAction;
  text: string;
  provider: string;
  model: string;
};

export const TEXT_TRANSFORM_LABELS: Record<TextTransformAction, string> = {
  rewrite: "改写",
  translate: "翻译",
  summarize: "总结",
  expand: "扩写",
};

export function textTransformRequestDefaults(action: TextTransformAction) {
  return {
    targetLanguage: action === "translate" ? "中文" : null,
    tone: action === "rewrite" || action === "expand" ? "professional" : null,
  };
}

export function textTransformResultFromResponse(
  sourceMessageId: number,
  response: TransformTextResponse,
): TextTransformResult {
  const action = normalizeTransformAction(response.action);
  return {
    id: `${sourceMessageId}-${action}-${Date.now()}`,
    sourceMessageId,
    action,
    text: response.text,
    provider: response.provider,
    model: response.model,
  };
}

export function normalizeTransformAction(value: string): TextTransformAction {
  if (value === "translate" || value === "summarize" || value === "expand") return value;
  return "rewrite";
}
