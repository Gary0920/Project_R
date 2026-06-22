import { useEffect, useMemo, useState } from "react";

import { listWorkspaceFiles } from "../api";
import {
  countPendingIngestFiles,
  filterSystemWorkspaceItems,
  findDirectory,
  getItemsAtPath,
  makeBreadcrumb,
  MEETING_ROOT_PATH,
  MEETING_WORKFLOW_DIRS,
} from "../workspaceFilePanelUtils";
import { isMeetingFolderPath } from "../workspaceMeetingUtils";
import type { ApiClientOptions } from "../../../shared/api/client";
import type { WorkspaceFileItemResponse } from "../../../shared/api/types";

export type WorkspaceFileViewMode = "files" | "trash";

export function useWorkspaceFileNavigation({
  apiOptions,
  closeFilePreview,
  defaultPath,
  standaloneCustomerIntelligence,
  workspaceId,
  workspaceKind,
}: {
  apiOptions: ApiClientOptions;
  closeFilePreview: () => void;
  defaultPath: string;
  standaloneCustomerIntelligence: boolean;
  workspaceId: number | null;
  workspaceKind: string;
}) {
  const [items, setItems] = useState<WorkspaceFileItemResponse[]>([]);
  const [currentPath, setCurrentPath] = useState(defaultPath);
  const [history, setHistory] = useState<string[]>([defaultPath || ""]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [viewMode, setViewMode] = useState<WorkspaceFileViewMode>("files");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const displayItems = useMemo(() => filterSystemWorkspaceItems(items), [items]);
  const visibleItems = useMemo(() => viewMode === "trash" ? items : getItemsAtPath(displayItems, currentPath), [currentPath, displayItems, items, viewMode]);
  const breadcrumb = useMemo(() => makeBreadcrumb(currentPath), [currentPath]);
  const pendingIngestCount = useMemo(() => countPendingIngestFiles(visibleItems), [visibleItems]);
  const isInMeetingFolder = useMemo(
    () => visibleItems.some((child) => child.type === "directory" && child.name === "02-转录文本"),
    [visibleItems],
  );
  const isMeetingRoot = currentPath === MEETING_ROOT_PATH || currentPath.startsWith(`${MEETING_ROOT_PATH}/`);
  const hasMeetingWorkflowDirs = MEETING_WORKFLOW_DIRS.some((name) =>
    visibleItems.some((item) => item.type === "directory" && item.name === name),
  );
  const isLegitimateMeetingFolder = isMeetingFolderPath(currentPath);
  const showMeetingWorkflowToolbar = workspaceKind !== "user" && viewMode === "files" && (isMeetingRoot || hasMeetingWorkflowDirs);
  const activeMeetingFolderPath = isLegitimateMeetingFolder ? MEETING_ROOT_PATH : currentPath;

  function navigateTo(path: string) {
    if (path === currentPath) return;
    closeFilePreview();
    setCurrentPath(path);
    setHistory((prev) => {
      const next = [...prev.slice(0, historyIndex + 1), path];
      setHistoryIndex(next.length - 1);
      return next;
    });
  }

  function goBack() {
    if (historyIndex <= 0) return;
    const nextIndex = historyIndex - 1;
    setHistoryIndex(nextIndex);
    setCurrentPath(history[nextIndex] ?? "");
  }

  function goForward() {
    if (historyIndex >= history.length - 1) return;
    const nextIndex = historyIndex + 1;
    setHistoryIndex(nextIndex);
    setCurrentPath(history[nextIndex] ?? "");
  }

  function goUp() {
    if (!currentPath) return;
    navigateTo(currentPath.split("/").slice(0, -1).join("/"));
  }

  function refresh() {
    if (!workspaceId) {
      setItems([]);
      setCurrentPath("");
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return listWorkspaceFiles(apiOptions, workspaceId, viewMode === "trash")
      .then((response) => {
        setItems(response.items);
        const safeItems = filterSystemWorkspaceItems(response.items);
        if (viewMode === "files" && currentPath && !findDirectory(safeItems, currentPath)) {
          navigateTo("");
        }
      })
      .catch((loadError: unknown) => {
        setError(loadError instanceof Error ? loadError.message : "无法读取项目文件目录");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (standaloneCustomerIntelligence) return;
    void refresh();
  }, [apiOptions, workspaceId, viewMode, standaloneCustomerIntelligence]);

  useEffect(() => {
    if (viewMode !== "files") return;
    const nextPath = defaultPath || "";
    setCurrentPath(nextPath);
    setHistory([nextPath]);
    setHistoryIndex(0);
  }, [defaultPath, workspaceId, viewMode]);

  useEffect(() => {
    if (viewMode !== "files" || !currentPath || loading) return;
    if (!findDirectory(displayItems, currentPath)) {
      setCurrentPath("");
      setHistory([""]);
      setHistoryIndex(0);
    }
  }, [currentPath, displayItems, loading, viewMode]);

  return {
    activeMeetingFolderPath,
    breadcrumb,
    currentPath,
    error,
    goBack,
    goForward,
    goUp,
    hasMeetingWorkflowDirs,
    history,
    historyIndex,
    isInMeetingFolder,
    isLegitimateMeetingFolder,
    isMeetingRoot,
    loading,
    navigateTo,
    pendingIngestCount,
    refresh,
    setCurrentPath,
    setError,
    setViewMode,
    showMeetingWorkflowToolbar,
    viewMode,
    visibleItems,
  };
}
