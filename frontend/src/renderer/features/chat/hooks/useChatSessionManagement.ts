import { useState, type Dispatch, type MouseEvent, type RefObject, type SetStateAction } from "react";

import { ApiError, type ApiClientOptions } from "../../../shared/api/client";
import type { ChatSessionResponse } from "../../../shared/api/types";
import type { ContextMenuItemDef } from "../../../shared/components/ContextMenu";
import {
  archiveChatSession,
  deleteChatSession,
  exportChatSession,
  listChatSessions,
  updateChatSession,
} from "../api";
import type { ChatMessage } from "../state";
import type { Tab } from "../tabs-state";

export type RenameScope = "header" | "sidebar";
export type RenameInput = { id: number; value: string; scope: RenameScope };
type SplitPaneKey = "left" | "right";
type WorkspaceItem = { id: number; workspace_name?: string; workspace_kind?: string };

export function useChatSessionManagement({
  activeSessionId,
  activeTabId,
  activeWorkspaceId,
  apiOptions,
  clearAuth,
  selectSession,
  sessions,
  setActionNotice,
  setActiveSessionId,
  setActiveTabId,
  setContextMenu,
  setError,
  setMessagesBySession,
  setSessions,
  setSplitPaneSessionIds,
  setTabs,
  sidebarRenameInputRef,
  tabs,
  titleInputRef,
  workspaces,
}: {
  activeSessionId: number | null;
  activeTabId: string;
  activeWorkspaceId: number | null;
  apiOptions: ApiClientOptions;
  clearAuth: () => void;
  selectSession: (session: ChatSessionResponse, openInNewTab?: boolean) => void;
  sessions: ChatSessionResponse[];
  setActionNotice: (notice: string) => void;
  setActiveSessionId: (sessionId: number | null) => void;
  setActiveTabId: (tabId: string) => void;
  setContextMenu: (menu: { x: number; y: number; items: ContextMenuItemDef[] } | null) => void;
  setError: (message: string) => void;
  setMessagesBySession: Dispatch<SetStateAction<Record<number, ChatMessage[]>>>;
  setSessions: Dispatch<SetStateAction<ChatSessionResponse[]>>;
  setSplitPaneSessionIds: Dispatch<SetStateAction<Record<SplitPaneKey, number | null>>>;
  setTabs: Dispatch<SetStateAction<Tab[]>>;
  sidebarRenameInputRef: RefObject<HTMLInputElement | null>;
  tabs: Tab[];
  titleInputRef: RefObject<HTMLInputElement | null>;
  workspaces: WorkspaceItem[];
}) {
  const [deleteConfirmSessionId, setDeleteConfirmSessionId] = useState<number | null>(null);
  const [moveSessionId, setMoveSessionId] = useState<number | null>(null);
  const [renameInput, setRenameInput] = useState<RenameInput | null>(null);

  async function handleDeleteSession(sessionId: number) {
    setError("");
    try {
      await deleteChatSession(apiOptions, sessionId);
      const nextSessions = sessions.filter((session) => session.id !== sessionId);
      setSessions(nextSessions);
      setMessagesBySession((current) => {
        const next = { ...current };
        delete next[sessionId];
        return next;
      });
      setTabs((current) => current.filter((tab) => tab.sessionId !== sessionId));
      setSplitPaneSessionIds((current) => ({
        left: current.left === sessionId ? null : current.left,
        right: current.right === sessionId ? null : current.right,
      }));
      if (activeSessionId === sessionId) setActiveSessionId(nextSessions[0]?.id ?? null);
    } catch (deleteError: unknown) {
      if (deleteError instanceof ApiError && deleteError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("删除会话失败，请稍后重试。");
    }
  }

  async function handlePinSession(sessionId: number) {
    const session = sessions.find((item) => item.id === sessionId);
    if (!session) return;
    const nextPinned = !session.is_pinned;
    setSessions((prev) => prev.map((item) => item.id === sessionId ? { ...item, is_pinned: nextPinned } : item));
    try {
      const updated = await updateChatSession(apiOptions, sessionId, { is_pinned: nextPinned });
      setSessions((prev) => prev.map((item) => item.id === sessionId ? updated : item));
    } catch {
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    }
  }

  function handleRenameSession(sessionId: number, scope: RenameScope = "sidebar") {
    const session = sessions.find((item) => item.id === sessionId);
    setRenameInput({ id: sessionId, value: session?.title ?? "", scope });
    window.requestAnimationFrame(() => {
      const input = scope === "header" ? titleInputRef.current : sidebarRenameInputRef.current;
      input?.focus();
      input?.select();
    });
  }

  async function commitRename() {
    if (!renameInput) return;
    const title = renameInput.value.trim();
    const current = sessions.find((item) => item.id === renameInput.id);
    if (!title || title === current?.title) {
      setRenameInput(null);
      return;
    }
    const sid = renameInput.id;
    setSessions((prev) => prev.map((item) => item.id === sid ? { ...item, title } : item));
    setTabs((prev) => prev.map((tab) => tab.sessionId === sid ? { ...tab, title } : tab));
    setRenameInput(null);
    try {
      const updated = await updateChatSession(apiOptions, sid, { title });
      setSessions((prev) => prev.map((item) => item.id === sid ? updated : item));
    } catch {
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    }
  }

  async function handleArchiveSession(sessionId: number) {
    try {
      await archiveChatSession(apiOptions, sessionId);
      const nextSessions = sessions.filter((item) => item.id !== sessionId);
      const archivedTabId = `chat-${sessionId}`;
      const nextTabs = tabs.filter((tab) => tab.sessionId !== sessionId);
      setSessions(nextSessions);
      setTabs(nextTabs);
      setMessagesBySession((prev) => {
        const next = { ...prev };
        delete next[sessionId];
        return next;
      });
      setSplitPaneSessionIds((current) => ({
        left: current.left === sessionId ? null : current.left,
        right: current.right === sessionId ? null : current.right,
      }));
      if (activeTabId === archivedTabId) {
        const nextTab = nextTabs[0];
        if (nextTab?.sessionId) {
          setActiveTabId(nextTab.id);
          setActiveSessionId(nextTab.sessionId);
        } else {
          setActiveTabId("");
          setActiveSessionId(nextSessions[0]?.id ?? null);
        }
      } else if (activeSessionId === sessionId) {
        setActiveSessionId(nextSessions[0]?.id ?? null);
      }
    } catch {
      setError("归档失败，请稍后重试。");
    }
  }

  async function handleMoveSession(sessionId: number, workspaceId: number) {
    try {
      await updateChatSession(apiOptions, sessionId, { workspace_id: workspaceId });
      const nextSessions = sessions.filter((item) => item.id !== sessionId);
      setSessions(nextSessions);
      setTabs((current) => current.filter((tab) => tab.sessionId !== sessionId));
      setSplitPaneSessionIds((current) => ({
        left: current.left === sessionId ? null : current.left,
        right: current.right === sessionId ? null : current.right,
      }));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setActiveTabId("");
      }
      setMoveSessionId(null);
    } catch {
      setError("迁移会话失败，请稍后重试。");
    }
  }

  function openSessionMenu(event: MouseEvent, session: ChatSessionResponse) {
    event.preventDefault();
    const moveTargets = workspaces.filter((workspace) => workspace.id !== session.workspace_id);
    const items: ContextMenuItemDef[] = [
      { type: "item", label: "在新标签页打开", action: () => selectSession(session, true) },
      { type: "separator" },
      { type: "item", label: session.is_pinned ? "取消置顶" : "置顶", action: () => void handlePinSession(session.id) },
      { type: "item", label: "重命名", action: () => handleRenameSession(session.id, "sidebar") },
      { type: "item", label: "归档", action: () => void handleArchiveSession(session.id) },
    ];
    if (moveTargets.length > 0) {
      items.push({ type: "separator" });
      items.push({ type: "item", label: "迁移项目", action: () => setMoveSessionId(session.id) });
    }
    items.push(
      { type: "separator" },
      {
        type: "item",
        label: "导出 Markdown",
        action: () => {
          setActionNotice("正在导出...");
          exportChatSession(apiOptions, session.id, "markdown")
            .then(() => setActionNotice(""))
            .catch((err: unknown) => {
              setActionNotice(err instanceof ApiError ? err.message : "导出失败");
            });
        },
      },
      {
        type: "item",
        label: "导出 JSON",
        action: () => {
          setActionNotice("正在导出...");
          exportChatSession(apiOptions, session.id, "json")
            .then(() => setActionNotice(""))
            .catch((err: unknown) => {
              setActionNotice(err instanceof ApiError ? err.message : "导出失败");
            });
        },
      },
      { type: "separator" },
      { type: "item", label: "删除", destructive: true, action: () => setDeleteConfirmSessionId(session.id) },
    );
    setContextMenu({ x: event.clientX, y: event.clientY, items });
  }

  return {
    commitRename,
    deleteConfirmSessionId,
    handleArchiveSession,
    handleDeleteSession,
    handleMoveSession,
    handlePinSession,
    handleRenameSession,
    moveSessionId,
    openSessionMenu,
    renameInput,
    setDeleteConfirmSessionId,
    setMoveSessionId,
    setRenameInput,
  };
}
