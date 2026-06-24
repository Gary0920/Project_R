import { describe, it, expect } from "vitest";
import { createStore } from "jotai";
import type { ChatSessionResponse } from "../../shared/api/types";
import {
  chatSessionsAtom,
  activeSessionIdAtom,
  chatMessagesBySessionAtom,
  activeSessionAtom,
  activeMessagesAtom,
  type ChatMessage,
} from "./state";

function makeStore() {
  return createStore();
}

/** 测试用最小会话对象 */
function mockSession(overrides: Partial<ChatSessionResponse> = {}): ChatSessionResponse {
  return {
    id: 1,
    title: "测试会话",
    workspace_id: null,
    is_archived: false,
    is_pinned: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** 测试用最小消息对象 */
function mockMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  const base: ChatMessage = {
    id: 1,
    session_id: 1,
    content: "你好",
    role: "user",
    provider: null,
    model: null,
    token_input: null,
    token_output: null,
    token_total: null,
    status: "success",
    error_message: null,
    rag_used: false,
    is_excluded: false,
    version_group_id: null,
    version_index: 0,
    version_count: 1,
    active_version: true,
    versions: [],
    feedback: null,
    feedback_rating: null,
    feedback_comment: null,
    sources: [],
    attachments: [],
    agent_run: null,
    context_trace: null,
    created_at: "2026-01-01T00:00:00Z",
  };
  return { ...base, ...overrides } as ChatMessage;
}

describe("chat state atoms", () => {
  it("activeSessionAtom returns null when no session matches", () => {
    const store = makeStore();
    store.set(chatSessionsAtom, []);
    store.set(activeSessionIdAtom, 1);

    const result = store.get(activeSessionAtom);
    expect(result).toBeNull();
  });

  it("activeSessionAtom returns the matching session", () => {
    const store = makeStore();
    const session = mockSession({ id: 1, title: "测试会话" });
    store.set(chatSessionsAtom, [session]);
    store.set(activeSessionIdAtom, 1);

    const result = store.get(activeSessionAtom);
    expect(result).not.toBeNull();
    expect(result!.title).toBe("测试会话");
  });

  it("activeMessagesAtom returns empty array when no active session", () => {
    const store = makeStore();
    store.set(activeSessionIdAtom, null);

    const result = store.get(activeMessagesAtom);
    expect(result).toEqual([]);
  });

  it("activeMessagesAtom returns messages for active session", () => {
    const store = makeStore();
    store.set(activeSessionIdAtom, 1);

    const messages = [mockMessage({ id: 1, content: "你好", role: "user" })];
    store.set(chatMessagesBySessionAtom, { 1: messages });

    const result = store.get(activeMessagesAtom);
    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("你好");
  });
});
