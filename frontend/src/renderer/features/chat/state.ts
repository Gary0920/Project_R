import { atom } from "jotai";

import type {
  ChatMessageResponse,
  ChatSessionResponse,
  ChatSourceResponse,
  GeneratedFileResponse,
  SkillRunResponse,
} from "../../shared/api/types";

export type ChatMessage = ChatMessageResponse & {
  isTyping?: boolean;
  isRegenerating?: boolean;
  isOptimistic?: boolean;
  sources?: ChatSourceResponse[];
  generated_file?: GeneratedFileResponse | null;
  skill_run?: SkillRunResponse | null;
  agent_suggestion?: {
    reason: string;
    request: string;
  } | null;
};

export const chatSessionsAtom = atom<ChatSessionResponse[]>([]);
export const activeSessionIdAtom = atom<number | null>(null);
export const chatMessagesBySessionAtom = atom<Record<number, ChatMessage[]>>({});
export const chatLoadingAtom = atom(false);
export const chatErrorAtom = atom<string | null>(null);

export const activeSessionAtom = atom((get) => {
  const activeSessionId = get(activeSessionIdAtom);
  return get(chatSessionsAtom).find((session) => session.id === activeSessionId) ?? null;
});

export const activeMessagesAtom = atom((get) => {
  const activeSessionId = get(activeSessionIdAtom);
  if (!activeSessionId) {
    return [];
  }
  return get(chatMessagesBySessionAtom)[activeSessionId] ?? [];
});
