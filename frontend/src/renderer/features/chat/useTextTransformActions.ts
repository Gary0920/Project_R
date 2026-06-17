import { useState, type RefObject } from "react";

import { ApiError, type ApiClientOptions } from "../../shared/api/client";
import { transformChatText } from "./api";
import type { ChatMessage } from "./state";
import type { ModelOption } from "./modelOptions";
import {
  textTransformRequestDefaults,
  textTransformResultFromResponse,
  type TextTransformAction,
  type TextTransformResult,
} from "./textTransform";

type CopyText = (text: string, preserveFormatting: boolean) => Promise<void>;

type TextTransformActionsOptions = {
  apiOptions: ApiClientOptions;
  clearAuth: () => void;
  copyText: CopyText;
  selectedModelOption: ModelOption | null;
  setActionNotice: (message: string) => void;
  setDraft: (text: string) => void;
  setError: (message: string) => void;
  setMessageActionBusyId: (id: number | null) => void;
  temperature: number | undefined;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  thinkingEnabled: boolean;
};

export function useTextTransformActions({
  apiOptions,
  clearAuth,
  copyText,
  selectedModelOption,
  setActionNotice,
  setDraft,
  setError,
  setMessageActionBusyId,
  temperature,
  textareaRef,
  thinkingEnabled,
}: TextTransformActionsOptions) {
  const [textTransformResult, setTextTransformResult] = useState<TextTransformResult | null>(null);

  async function handleTransformMessage(message: ChatMessage, action: TextTransformAction) {
    const text = message.content.trim();
    if (!text) return;
    setMessageActionBusyId(message.id);
    setError("");
    try {
      const defaults = textTransformRequestDefaults(action);
      const result = await transformChatText(apiOptions, {
        text,
        action,
        modelProfile: selectedModelOption?.profile ?? null,
        provider: selectedModelOption?.provider ?? null,
        targetLanguage: defaults.targetLanguage,
        tone: defaults.tone,
        thinking: thinkingEnabled,
        temperature,
      });
      setTextTransformResult(textTransformResultFromResponse(message.id, result));
      textareaRef.current?.focus();
      setActionNotice("已生成文本变换结果，请确认后替换输入框或复制。");
    } catch (transformError: unknown) {
      if (transformError instanceof ApiError && transformError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("文本变换失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  function handleApplyTextTransformResult(text: string) {
    setDraft(text);
    setTextTransformResult(null);
    textareaRef.current?.focus();
  }

  async function handleCopyTextTransformResult(text: string) {
    await copyText(text, false);
  }

  return {
    clearTextTransformResult: () => setTextTransformResult(null),
    handleApplyTextTransformResult,
    handleCopyTextTransformResult,
    handleTransformMessage,
    textTransformResult,
  };
}
