import { act, renderHook, waitFor } from "@testing-library/react";
import { useCallback, useMemo, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePageDataLoader } from "./usePageDataLoader";
import type {
  ChatMessageResponse,
  ChatSearchResultResponse,
  ChatSessionResponse,
  SkillResponse,
} from "../../../shared/api/types";

const chatApi = vi.hoisted(() => ({
  listChatMessages: vi.fn(),
  listChatSessions: vi.fn(),
  searchChatSessions: vi.fn(),
}));

const skillsApi = vi.hoisted(() => ({
  listSkills: vi.fn(),
}));

vi.mock("../api", () => chatApi);
vi.mock("../../skills/api", () => skillsApi);

function mockSession(overrides: Partial<ChatSessionResponse> = {}): ChatSessionResponse {
  return {
    id: 1,
    title: "会话",
    workspace_id: 7,
    is_archived: false,
    is_pinned: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockMessage(overrides: Partial<ChatMessageResponse> = {}): ChatMessageResponse {
  return {
    id: 10,
    session_id: 1,
    role: "assistant",
    content: "回复",
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
    ...overrides,
  };
}

function useLoaderHarness(initial?: {
  activeSessionId?: number | null;
  activeWorkspaceId?: number | null;
  messagesBySession?: Record<number, ChatMessageResponse[]>;
  searchTerm?: string;
  showSearch?: boolean;
}) {
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(initial?.activeSessionId ?? null);
  const [messagesBySession, setMessagesBySession] = useState<Record<number, ChatMessageResponse[]>>(
    initial?.messagesBySession ?? {},
  );
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [searchResults, setSearchResults] = useState<ChatSearchResultResponse[]>([]);
  const [tabs, setTabs] = useState<{ id: string; sessionId: number | null; workspaceId: number | null; title: string }[]>([]);
  const [activeTabId, setActiveTabId] = useState("");
  const [splitPaneSessionIds, setSplitPaneSessionIds] = useState<Record<"left" | "right", number | null>>({
    left: null,
    right: null,
  });
  const [showScratchPad, setShowScratchPad] = useState(true);
  const apiOptions = useMemo(() => ({ baseUrl: "http://api.test", token: "token" }), []);
  const clearAuth = useCallback(() => undefined, []);

  const actions = usePageDataLoader({
    apiOptions,
    activeWorkspaceId: initial?.activeWorkspaceId ?? null,
    activeSessionId,
    messagesBySession,
    setSessions,
    setIsLoading,
    setError,
    setActiveSessionId,
    clearAuth,
    setMessagesBySession,
    setSkills,
    showSearch: initial?.showSearch ?? false,
    searchTerm: initial?.searchTerm ?? "",
    setSearchResults,
    activeTabId,
    setActiveTabId,
    sideBySideOpen: true,
    activeSplitPane: "left",
    setSplitPaneSessionIds,
    setTabs,
    setShowScratchPad,
  });

  return {
    actions,
    state: {
      activeSessionId,
      activeTabId,
      error,
      isLoading,
      messagesBySession,
      searchResults,
      sessions,
      showScratchPad,
      skills,
      splitPaneSessionIds,
      tabs,
    },
  };
}

describe("usePageDataLoader", () => {
  beforeEach(() => {
    chatApi.listChatMessages.mockReset();
    chatApi.listChatSessions.mockReset();
    chatApi.searchChatSessions.mockReset();
    chatApi.listChatMessages.mockResolvedValue({ items: [] });
    chatApi.listChatSessions.mockResolvedValue([]);
    skillsApi.listSkills.mockReset();
    skillsApi.listSkills.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads sessions when the workspace changes", async () => {
    chatApi.listChatSessions.mockResolvedValue([mockSession({ id: 3, workspace_id: 7 })]);

    const { result } = renderHook(() => useLoaderHarness({ activeWorkspaceId: 7 }));

    await waitFor(() => expect(result.current.state.sessions).toHaveLength(1));
    expect(chatApi.listChatSessions).toHaveBeenCalledWith(
      expect.objectContaining({ token: "token" }),
      7,
    );
    expect(result.current.state.sessions[0].id).toBe(3);
    expect(result.current.state.error).toBeNull();
  });

  it("loads messages for an active session when they are not cached", async () => {
    chatApi.listChatMessages.mockResolvedValue({ items: [mockMessage({ id: 22, session_id: 42 })] });
    const setMessagesBySession = vi.fn();

    renderHook(() =>
      usePageDataLoader({
        apiOptions: { baseUrl: "http://api.test", token: "token" },
        activeWorkspaceId: null,
        activeSessionId: 42,
        messagesBySession: {},
        setSessions: vi.fn(),
        setIsLoading: vi.fn(),
        setError: vi.fn(),
        setActiveSessionId: vi.fn(),
        clearAuth: vi.fn(),
        setMessagesBySession,
        setSkills: vi.fn(),
        showSearch: false,
        searchTerm: "",
        setSearchResults: vi.fn(),
        activeTabId: "",
        setActiveTabId: vi.fn(),
        sideBySideOpen: false,
        activeSplitPane: "left",
        setSplitPaneSessionIds: vi.fn(),
        setTabs: vi.fn(),
        setShowScratchPad: vi.fn(),
      }),
    );

    await waitFor(() => expect(setMessagesBySession).toHaveBeenCalled());
    expect(chatApi.listChatMessages).toHaveBeenCalledWith(expect.objectContaining({ token: "token" }), 42);
    const updater = setMessagesBySession.mock.calls.at(-1)?.[0] as (
      current: Record<number, ChatMessageResponse[]>,
    ) => Record<number, ChatMessageResponse[]>;
    expect(updater({})[42][0].id).toBe(22);
  });

  it("debounces session search and stores results", async () => {
    vi.useFakeTimers();
    const searchResult = mockSession({ id: 9, title: "搜索命中" }) as ChatSearchResultResponse;
    searchResult.matched_message = "关键词";
    chatApi.searchChatSessions.mockResolvedValue([searchResult]);

    const { result } = renderHook(() =>
      useLoaderHarness({ activeWorkspaceId: 7, showSearch: true, searchTerm: "关键词" }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(180);
    });

    expect(result.current.state.searchResults).toHaveLength(1);
    expect(chatApi.searchChatSessions).toHaveBeenCalledWith(
      expect.objectContaining({ token: "token" }),
      "关键词",
      7,
    );
  });

  it("selectSession opens a session in the active split pane and tab list", () => {
    const session = mockSession({ id: 12, workspace_id: 7, title: "目标会话" });
    const { result } = renderHook(() => useLoaderHarness({ activeWorkspaceId: 7 }));

    act(() => result.current.actions.selectSession(session));

    expect(result.current.state.activeSessionId).toBe(12);
    expect(result.current.state.activeTabId).toBe("chat-12");
    expect(result.current.state.splitPaneSessionIds.left).toBe(12);
    expect(result.current.state.tabs).toEqual([
      { id: "chat-12", sessionId: 12, workspaceId: 7, title: "目标会话" },
    ]);
    expect(result.current.state.showScratchPad).toBe(false);
  });
});
