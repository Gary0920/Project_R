import { useEffect, useState } from "react";

/** 会话草稿持久化 —— 按 sessionId 读写 localStorage，防止刷新/切换丢失输入。 */

const DRAFT_PREFIX = "chat_draft_";

export function loadDraft(sessionId: number | null | undefined): string {
  if (!sessionId) return "";
  try {
    return localStorage.getItem(DRAFT_PREFIX + sessionId) ?? "";
  } catch {
    return "";
  }
}

export function saveDraft(sessionId: number | null | undefined, value: string): void {
  if (!sessionId) return;
  try {
    if (value.trim() === "") {
      localStorage.removeItem(DRAFT_PREFIX + sessionId);
    } else {
      localStorage.setItem(DRAFT_PREFIX + sessionId, value);
    }
  } catch {
    // storage 满/不可用 — 静默降级
  }
}

export function clearDraft(sessionId: number | null | undefined): void {
  if (!sessionId) return;
  try {
    localStorage.removeItem(DRAFT_PREFIX + sessionId);
  } catch {
    // 忽略
  }
}

export function useChatDraft(sessionId: number | null | undefined) {
  const [draft, setDraft] = useState(() => loadDraft(sessionId));

  useEffect(() => {
    setDraft(loadDraft(sessionId));
  }, [sessionId]);

  useEffect(() => {
    const timer = setTimeout(() => saveDraft(sessionId, draft), 500);
    return () => clearTimeout(timer);
  }, [draft, sessionId]);

  return [draft, setDraft, () => clearDraft(sessionId)] as const;
}
