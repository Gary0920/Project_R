/**
 * Data loading effects extracted from AppPage.
 *
 * Encapsulates session list loading (per workspace), message history loading
 * (per active session), skill list loading, and session search.
 */
import { useEffect, type Dispatch, type SetStateAction } from "react";
import { ApiError, type ApiClientOptions } from "../../../shared/api/client";
import { listChatSessions, listChatMessages, searchChatSessions } from "../api";
import { listSkills } from "../../skills/api";
import type {
  ChatMessageResponse,
  ChatSearchResultResponse,
  ChatSessionResponse,
  SkillResponse,
} from "../../../shared/api/types";

export interface PageDataLoaderDeps {
  apiOptions: ApiClientOptions;
  activeWorkspaceId: number | null;
  activeSessionId: number | null;
  messagesBySession: Record<number, ChatMessageResponse[]>;
  // Session loading
  setSessions: Dispatch<SetStateAction<ChatSessionResponse[]>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setActiveSessionId: (id: number | null) => void;
  clearAuth: () => void;
  // Message loading
  setMessagesBySession: Dispatch<SetStateAction<Record<number, ChatMessageResponse[]>>>;
  // Skills
  setSkills: Dispatch<SetStateAction<SkillResponse[]>>;
  // Search
  showSearch: boolean;
  searchTerm: string;
  setSearchResults: Dispatch<SetStateAction<ChatSearchResultResponse[]>>;
  // Tab helpers (for selectSession)
  activeTabId: string;
  setActiveTabId: (id: string) => void;
  sideBySideOpen: boolean;
  activeSplitPane: "left" | "right";
  setSplitPaneSessionIds: Dispatch<
    SetStateAction<Record<"left" | "right", number | null>>
  >;
  setTabs: Dispatch<SetStateAction<{ id: string; sessionId: number | null; workspaceId: number | null; title: string }[]>>;
  setShowScratchPad: Dispatch<SetStateAction<boolean>>;
}

export function usePageDataLoader(deps: PageDataLoaderDeps) {
  const {
    apiOptions, activeWorkspaceId, activeSessionId, messagesBySession,
    setSessions, setIsLoading, setError, setActiveSessionId, clearAuth,
    setMessagesBySession,
    setSkills,
    showSearch, searchTerm, setSearchResults,
    activeTabId, setActiveTabId,
    sideBySideOpen, activeSplitPane, setSplitPaneSessionIds,
    setTabs, setShowScratchPad,
  } = deps;

  // ── Session list loading (reloads on workspace change) ────────────────

  useEffect(() => {
    let mounted = true;
    setIsLoading(true);
    setError(null);
    setSessions([]);
    setActiveSessionId(null);
    if (!activeWorkspaceId) {
      setIsLoading(false);
      return;
    }
    listChatSessions(apiOptions, activeWorkspaceId)
      .then((loadedSessions) => {
        if (!mounted) return;
        setSessions(loadedSessions);
        setError(null);
      })
      .catch((loadError: unknown) => {
        if (!mounted) return;
        if (loadError instanceof ApiError && loadError.status === 401) {
          clearAuth();
          window.location.hash = "#/login";
          return;
        }
        setError("无法加载会话列表，请确认后端正在运行。");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [activeWorkspaceId, apiOptions, clearAuth, setActiveSessionId, setError, setIsLoading, setSessions]);

  // ── Skill list loading (once on mount) ────────────────────────────────

  useEffect(() => {
    let mounted = true;
    listSkills(apiOptions)
      .then((items) => {
        if (mounted) setSkills(items);
      })
      .catch(() => {
        if (mounted) setSkills([]);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  // ── Message loading (when active session changes) ─────────────────────

  useEffect(() => {
    if (!activeSessionId || messagesBySession[activeSessionId]) return;
    let mounted = true;
    setIsLoading(true);
    setError(null);
    listChatMessages(apiOptions, activeSessionId)
      .then((response) => {
        if (!mounted) return;
        setMessagesBySession((current) => ({ ...current, [activeSessionId]: response.items }));
        setError(null);
      })
      .catch((loadError: unknown) => {
        if (!mounted) return;
        if (loadError instanceof ApiError && loadError.status === 401) {
          clearAuth();
          window.location.hash = "#/login";
          return;
        }
        setError("无法读取消息历史，请稍后重试。");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [activeSessionId, apiOptions, clearAuth, messagesBySession, setError, setIsLoading, setMessagesBySession]);

  // ── Session search (debounced) ────────────────────────────────────────

  useEffect(() => {
    if (!showSearch || !searchTerm.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      searchChatSessions(apiOptions, searchTerm, activeWorkspaceId)
        .then(setSearchResults)
        .catch(() => setSearchResults([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [activeWorkspaceId, apiOptions, searchTerm, showSearch]);

  // ── Session selection helper ──────────────────────────────────────────

  function selectSession(session: ChatSessionResponse, openInNewTab = false) {
    setShowScratchPad(false);
    setActiveSessionId(session.id);
    if (sideBySideOpen) {
      setSplitPaneSessionIds((current) => ({ ...current, [activeSplitPane]: session.id }));
    }
    const tabId = `chat-${session.id}`;
    setTabs((current) => {
      const existing = current.find((tab) => tab.id === tabId);
      if (existing) return current;
      const nextTab = {
        id: tabId,
        sessionId: session.id,
        workspaceId: session.workspace_id,
        title: session.title,
      };
      const activeTab = current.find((tab) => tab.id === activeTabId);
      if (activeTab?.sessionId === null && activeTab.id.startsWith("draft-")) {
        return current.map((tab) => tab.id === activeTabId ? nextTab : tab);
      }
      if (openInNewTab || !activeTabId) return [...current, nextTab];
      if (!current.some((tab) => tab.id === activeTabId)) return [...current, nextTab];
      return current.map((tab) => tab.id === activeTabId ? nextTab : tab);
    });
    setActiveTabId(tabId);
  }

  return { selectSession } as const;
}
