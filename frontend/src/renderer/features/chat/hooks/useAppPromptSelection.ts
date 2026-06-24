import { useEffect, useMemo, useState, type RefObject } from "react";

import type { CompanyPromptResponse } from "../../../shared/api/types";
import type { ApiClientOptions } from "../../../shared/api/client";
import { getPromptOptionId, type PromptOption } from "../../prompts/components/PromptPanel";
import { PROJECT_R_BUILTIN_PROMPT } from "../../prompts/constants";
import { listCompanyPrompts } from "../../prompts/api";
import {
  PROMPT_SELECTION_KEY,
  makePromptId,
  readPromptSelectionMap,
} from "../../prompts/sessionPrompt";

export function useAppPromptSelection({
  activeSessionId,
  apiOptions,
  setUtilityPanel,
  textareaRef,
}: {
  activeSessionId: number | null;
  apiOptions: ApiClientOptions;
  setUtilityPanel: (panel: null) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const [companyPrompts, setCompanyPrompts] = useState<CompanyPromptResponse[]>([]);
  const [userPrompts, setUserPrompts] = useState<UserPromptRecord[]>([]);
  const [promptSelections, setPromptSelections] = useState<Record<string, string>>(readPromptSelectionMap);
  const [pendingPromptId, setPendingPromptId] = useState<string | null>(null);
  const promptOptions = useMemo<PromptOption[]>(() => [
    PROJECT_R_BUILTIN_PROMPT,
    ...companyPrompts.map((prompt) => ({
      id: prompt.id,
      source: "company" as const,
      name: prompt.name,
      description: prompt.description,
      content: prompt.content,
    })),
    ...userPrompts.map((prompt) => ({
      id: prompt.id,
      source: "user" as const,
      name: prompt.name,
      description: "仅本机可用",
      content: prompt.content,
    })),
  ], [companyPrompts, userPrompts]);
  const defaultPromptId = makePromptId(PROJECT_R_BUILTIN_PROMPT.source, PROJECT_R_BUILTIN_PROMPT.id);
  const selectedPromptId = activeSessionId
    ? promptSelections[String(activeSessionId)] ?? defaultPromptId
    : pendingPromptId ?? defaultPromptId;
  const matchedPrompt = promptOptions.find((prompt) => getPromptOptionId(prompt) === selectedPromptId);
  const selectedPrompt = matchedPrompt ?? PROJECT_R_BUILTIN_PROMPT;
  const selectedPromptIsDefault = !matchedPrompt || selectedPromptId === defaultPromptId;

  useEffect(() => {
    let mounted = true;
    listCompanyPrompts(apiOptions)
      .then((items) => {
        if (mounted) setCompanyPrompts(items);
      })
      .catch(() => {
        if (mounted) setCompanyPrompts([]);
      });
    window.projectR?.prompts?.listUser()
      .then((items) => {
        if (mounted) setUserPrompts(items);
      })
      .catch(() => {
        if (mounted) setUserPrompts([]);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  function storePromptSelection(sessionId: number, promptId: string) {
    setPromptSelections((current) => {
      const next = { ...current, [String(sessionId)]: promptId };
      localStorage.setItem(PROMPT_SELECTION_KEY, JSON.stringify(next));
      return next;
    });
  }

  function clearPromptSelection() {
    if (!activeSessionId) {
      setPendingPromptId(null);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    setPromptSelections((current) => {
      const next = { ...current };
      delete next[String(activeSessionId)];
      localStorage.setItem(PROMPT_SELECTION_KEY, JSON.stringify(next));
      return next;
    });
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function handleSelectPrompt(prompt: PromptOption) {
    const promptId = getPromptOptionId(prompt);
    if (!activeSessionId) {
      setPendingPromptId(promptId);
      setUtilityPanel(null);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    storePromptSelection(activeSessionId, promptId);
    setUtilityPanel(null);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function handleCreateUserPrompt(name: string, content: string) {
    const saved = await window.projectR?.prompts?.saveUser({ name, content });
    if (!saved) return null;
    setUserPrompts((prev) => [saved, ...prev.filter((item) => item.id !== saved.id)]);
    return saved;
  }

  async function handleUpdateUserPrompt(id: string, name: string, content: string) {
    const saved = await window.projectR?.prompts?.saveUser({ id, name, content });
    if (!saved) return null;
    setUserPrompts((prev) => [saved, ...prev.filter((item) => item.id !== saved.id)]);
    return saved;
  }

  async function handleDeleteUserPrompt(id: string) {
    const next = await window.projectR?.prompts?.deleteUser(id);
    setUserPrompts(next ?? []);
    if (activeSessionId && promptSelections[String(activeSessionId)] === makePromptId("user", id)) {
      handleSelectPrompt(PROJECT_R_BUILTIN_PROMPT);
    }
    if (pendingPromptId === makePromptId("user", id)) {
      setPendingPromptId(null);
    }
  }

  return {
    clearPromptSelection,
    companyPrompts,
    defaultPromptId,
    handleCreateUserPrompt,
    handleDeleteUserPrompt,
    handleSelectPrompt,
    handleUpdateUserPrompt,
    pendingPromptId,
    promptSelections,
    promptOptions,
    selectedPrompt,
    selectedPromptId,
    selectedPromptIsDefault,
    setPendingPromptId,
    storePromptSelection,
    userPrompts,
  };
}
