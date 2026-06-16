import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";

import type { ChatMessage } from "./state";

type MessagesBySession = Record<number, ChatMessage[]>;
type SendingSessions = Record<number, boolean>;

type UseChatStreamControlsOptions = {
  setMessagesBySession: Dispatch<SetStateAction<MessagesBySession>>;
  setSendingSessions: Dispatch<SetStateAction<SendingSessions>>;
};

export function isAbortError(value: unknown) {
  return value instanceof DOMException && value.name === "AbortError";
}

export function useChatStreamControls({
  setMessagesBySession,
  setSendingSessions,
}: UseChatStreamControlsOptions) {
  const sendAbortControllersRef = useRef<Map<number, AbortController>>(new Map());
  const typingTimersRef = useRef<Map<number, ReturnType<typeof window.setInterval>>>(new Map());

  useEffect(() => {
    return () => {
      for (const controller of sendAbortControllersRef.current.values()) {
        controller.abort();
      }
      sendAbortControllersRef.current.clear();
      for (const timer of typingTimersRef.current.values()) {
        window.clearInterval(timer);
      }
      typingTimersRef.current.clear();
    };
  }, []);

  function setSessionSending(sessionId: number, value: boolean) {
    setSendingSessions((current) => {
      const next = { ...current };
      if (value) next[sessionId] = true;
      else delete next[sessionId];
      return next;
    });
  }

  function registerSendAbortController(sessionId: number, controller: AbortController) {
    sendAbortControllersRef.current.set(sessionId, controller);
  }

  function finishSessionSend(sessionId: number) {
    sendAbortControllersRef.current.delete(sessionId);
    setSessionSending(sessionId, false);
  }

  function typeAssistantReply(sessionId: number, message: ChatMessage, fullText: string) {
    const existingTimer = typingTimersRef.current.get(sessionId);
    if (existingTimer) {
      window.clearInterval(existingTimer);
      typingTimersRef.current.delete(sessionId);
    }
    let index = 0;
    const timer = window.setInterval(() => {
      index += 3;
      setMessagesBySession((current) => ({
        ...current,
        [sessionId]: (current[sessionId] ?? []).map((item) =>
          item.id === message.id
            ? { ...item, content: fullText.slice(0, index), isTyping: index < fullText.length }
            : item,
        ),
      }));
      if (index >= fullText.length) {
        window.clearInterval(timer);
        typingTimersRef.current.delete(sessionId);
      }
    }, 18);
    typingTimersRef.current.set(sessionId, timer);
  }

  function updateStreamPlaceholder(sessionId: number, placeholderId: number, content: string) {
    setMessagesBySession((current) => ({
      ...current,
      [sessionId]: (current[sessionId] ?? []).map((message) =>
        message.id === placeholderId ? { ...message, content, isTyping: true } : message,
      ),
    }));
  }

  function removeStreamPlaceholder(sessionId: number, placeholderId: number | null) {
    if (placeholderId == null) return;
    setMessagesBySession((current) => ({
      ...current,
      [sessionId]: (current[sessionId] ?? []).filter((message) => message.id !== placeholderId),
    }));
  }

  function cancelSessionSend(sessionId: number | null | undefined) {
    if (!sessionId) return;
    sendAbortControllersRef.current.get(sessionId)?.abort();
    sendAbortControllersRef.current.delete(sessionId);
    const typingTimer = typingTimersRef.current.get(sessionId);
    if (typingTimer) {
      window.clearInterval(typingTimer);
      typingTimersRef.current.delete(sessionId);
      setMessagesBySession((current) => ({
        ...current,
        [sessionId]: (current[sessionId] ?? []).map((message) =>
          message.isTyping ? { ...message, isTyping: false } : message,
        ),
      }));
    }
    setSessionSending(sessionId, false);
  }

  return {
    cancelSessionSend,
    finishSessionSend,
    registerSendAbortController,
    removeStreamPlaceholder,
    setSessionSending,
    typeAssistantReply,
    updateStreamPlaceholder,
  };
}
