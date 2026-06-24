/**
 * Tab navigation and workspace switching logic extracted from AppPage.
 *
 * Centralises tab selection, close, workspace-change handlers and the
 * associated side-effect cleanups (scratch tab removal, source preview
 * dismissal on session switch).
 */
import { useEffect, type Dispatch, type SetStateAction } from "react";
import type { Tab } from "../tabs-state";
import type { SourcePreview } from "../messageContent";

export interface TabNavigationDeps {
  tabs: Tab[];
  setTabs: Dispatch<SetStateAction<Tab[]>>;
  activeTabId: string;
  setActiveTabId: (id: string) => void;
  activeSessionId: number | null;
  setActiveSessionId: (id: number | null) => void;
  activeWorkspaceId: number | null;
  setActiveWorkspaceId: (id: number | null) => void;
  sideBySideOpen: boolean;
  activeSplitPane: "left" | "right";
  setSplitPaneSessionIds: Dispatch<
    SetStateAction<Record<"left" | "right", number | null>>
  >;
  utilityPanel: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setUtilityPanel: Dispatch<SetStateAction<any>>;
  sourcePreview: SourcePreview | null;
  setSourcePreview: Dispatch<SetStateAction<SourcePreview | null>>;
  setShowScratchPad: Dispatch<SetStateAction<boolean>>;
  setMode: (mode: "chat" | "agent") => void;
}

export function useTabNavigation(deps: TabNavigationDeps) {
  const {
    tabs, setTabs,
    activeTabId, setActiveTabId,
    activeSessionId, setActiveSessionId,
    activeWorkspaceId, setActiveWorkspaceId,
    sideBySideOpen, activeSplitPane, setSplitPaneSessionIds,
    utilityPanel, setUtilityPanel,
    sourcePreview, setSourcePreview,
    setShowScratchPad,
    setMode,
  } = deps;

  // ── Effects ───────────────────────────────────────────────────────────

  // Clear source preview when switching away from its session
  useEffect(() => {
    if (
      utilityPanel === "source" &&
      sourcePreview?.sessionId != null &&
      sourcePreview.sessionId !== activeSessionId
    ) {
      setSourcePreview(null);
      setUtilityPanel(null);
    }
  }, [activeSessionId, sourcePreview?.sessionId, utilityPanel, setSourcePreview, setUtilityPanel]);

  // Remove scratch tab when it's no longer active
  useEffect(() => {
    setTabs((current: Tab[]) => {
      if (!current.some((tab) => tab.id === "scratch")) return current;
      return current.filter((tab) => tab.id !== "scratch");
    });
    if (activeTabId === "scratch") {
      setActiveTabId("");
      setActiveSessionId(null);
    }
  }, [activeTabId, setActiveSessionId, setActiveTabId, setTabs]);

  // ── Handlers ──────────────────────────────────────────────────────────

  function handleSelectTab(id: string) {
    setShowScratchPad(false);
    setActiveTabId(id);
    const tab = tabs.find((item) => item.id === id);
    if (tab?.sessionId) {
      setActiveSessionId(tab.sessionId);
      if (sideBySideOpen) {
        setSplitPaneSessionIds((current) => ({
          ...current,
          [activeSplitPane]: tab.sessionId ?? null,
        }));
      }
      if (tab.workspaceId && tab.workspaceId !== activeWorkspaceId) {
        setActiveWorkspaceId(tab.workspaceId);
      }
    } else if (tab) {
      setActiveSessionId(null);
      if (tab.workspaceId && tab.workspaceId !== activeWorkspaceId) {
        setActiveWorkspaceId(tab.workspaceId);
      }
      if (sideBySideOpen) {
        setSplitPaneSessionIds((current) => ({
          ...current,
          [activeSplitPane]: null,
        }));
      }
    }
  }

  function handleCloseTab(id: string) {
    const tab = tabs.find((item) => item.id === id);
    if (!tab) return;
    const nextTabs = tabs.filter((item) => item.id !== id);
    setTabs(nextTabs);
    if (activeTabId === id) {
      const next = nextTabs[0];
      if (next) handleSelectTab(next.id);
      else {
        setActiveTabId("");
        setActiveSessionId(null);
      }
    }
  }

  function handleWorkspaceChanged(workspaceId: number | null) {
    setActiveWorkspaceId(workspaceId);
    const tab = tabs.find((item) => item.id === activeTabId);
    if (tab?.sessionId && tab.workspaceId !== workspaceId) {
      setActiveTabId("");
      setActiveSessionId(null);
    }
  }

  function handleSwitchToAgent(_messageId: number) {
    setMode("agent");
  }

  return {
    handleSelectTab,
    handleCloseTab,
    handleWorkspaceChanged,
    handleSwitchToAgent,
  } as const;
}
