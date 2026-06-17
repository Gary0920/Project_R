import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";

import { WorkspaceAgentRunToast } from "./WorkspaceAgentRunToast";
import {
  WorkspaceConfirmationCard,
  WorkspaceTextPromptDialog,
  type WorkspaceConfirmation,
  type WorkspaceTextPrompt,
} from "./WorkspaceDialogs";
import { WorkspaceFilePreviewSidecar } from "./WorkspaceFilePreviewSidecar";
import {
  WorkspaceMeetingFolderDialog,
} from "./WorkspaceMeetingFolderDialog";
import {
  WorkspaceMeetingTranscriptDialog,
} from "./WorkspaceMeetingTranscriptDialog";
import {
  WorkspaceMeetingTermCorrectionsDialog,
} from "./WorkspaceMeetingTermCorrectionsDialog";
import { WorkspaceMeetingSpeakerMapDialog } from "./WorkspaceMeetingSpeakerMapDialog";
import { WorkspaceMeetingToolbar } from "./WorkspaceMeetingToolbar";
import { WorkspaceUploadProgress } from "./WorkspaceUploadProgress";
import { WorkspaceTrashTable } from "./WorkspaceTrashTable";
import { WorkspaceFileRow } from "./WorkspaceFileRow";
import { WorkspaceFileBreadcrumb } from "./WorkspaceFileBreadcrumb";
import { WorkspaceFileContextMenu } from "./WorkspaceFileContextMenu";
import { WorkspaceCustomerIntelligenceOverlay } from "./WorkspaceCustomerIntelligenceOverlay";
import { WorkspaceFilePanelHeader } from "./WorkspaceFilePanelHeader";
import { WorkspaceKnowledgeMapOverlay } from "./WorkspaceKnowledgeMapOverlay";
import { WorkspaceKnowledgeGraphSidecar } from "./WorkspaceKnowledgeGraphSidecar";
import type { WorkspaceFileContextMenu as WorkspaceFileContextMenuState } from "./workspaceFilePanelTypes";
import { listWorkspaceFiles } from "../api";
import {
  countPendingIngestFiles,
  filterSystemWorkspaceItems,
  findDirectory,
  getItemsAtPath,
  getRagStatusMeta,
  hasExternalFiles,
  hasWorkspaceDrag,
  isTrashPath,
  isTrashWorkspaceItem,
  makeBreadcrumb,
  MEETING_ROOT_PATH,
  MEETING_WORKFLOW_DIRS,
} from "../workspaceFilePanelUtils";
import {
  inferMeetingFolder,
  isInMeetingWorkflowPath,
  isMeetingAudioFile,
  isMeetingFolderPath,
  isMeetingTranscriptSourceFile,
  isMeetingWorkflowSubdirName,
} from "../workspaceMeetingUtils";
import { useWorkspaceFilePreview } from "../hooks/useWorkspaceFilePreview";
import { useWorkspacePreviewWidth } from "../hooks/useWorkspacePreviewWidth";
import { useKnowledgeGraphCanvas } from "../hooks/useKnowledgeGraphCanvas";
import { useWorkspaceKnowledgeGraph } from "../hooks/useWorkspaceKnowledgeGraph";
import { useWorkspaceMeetingWorkflow } from "../hooks/useWorkspaceMeetingWorkflow";
import { useWorkspaceFileActions } from "../hooks/useWorkspaceFileActions";
import { useWorkspaceFileDragDrop } from "../hooks/useWorkspaceFileDragDrop";
import type { ApiClientOptions } from "../../../shared/api/client";
import type { AgentRunResponse, WorkspaceFileItemResponse } from "../../../shared/api/types";
import { parseApiDate } from "../../../shared/utils/time";

export type WorkspaceFilePanelProps = {
  apiOptions: ApiClientOptions;
  workspaceId: number | null;
  workspaceName?: string;
  workspaceKind?: string;
  canIngestKnowledge?: boolean;
  defaultPath?: string;
  onReferenceFile?: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  onPreviewOpen?: () => void;
  onPreviewClose?: () => void;
  standaloneCustomerIntelligence?: boolean;
  onCustomerIntelligenceClose?: () => void;
};

export function WorkspaceFilePanel({
  apiOptions,
  workspaceId,
  workspaceName,
  workspaceKind = "project",
  canIngestKnowledge = false,
  defaultPath = "",
  onReferenceFile,
  onPreviewOpen,
  onPreviewClose,
  standaloneCustomerIntelligence = false,
  onCustomerIntelligenceClose,
}: WorkspaceFilePanelProps) {
  const [items, setItems] = useState<WorkspaceFileItemResponse[]>([]);
  const [currentPath, setCurrentPath] = useState(defaultPath);
  const [history, setHistory] = useState<string[]>([defaultPath || ""]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"files" | "trash">("files");
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [latestAgentRun, setLatestAgentRun] = useState<AgentRunResponse | null>(null);
  const [agentRunToastExpanded, setAgentRunToastExpanded] = useState(false);
  const [agentRunToastLeaving, setAgentRunToastLeaving] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<WorkspaceConfirmation | null>(null);
  const [confirmationBusy, setConfirmationBusy] = useState(false);
  const [refreshingKnowledge, setRefreshingKnowledge] = useState(false);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<WorkspaceFileContextMenuState | null>(null);
  const [compactActions, setCompactActions] = useState(false);
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const isPersonalWorkspace = workspaceKind === "user";
  const isCustomerWorkspace = workspaceKind === "customer";
  const { filePreview, closeFilePreview, openFilePreview } = useWorkspaceFilePreview({
    apiOptions,
    workspaceId,
    onPreviewOpen,
    onPreviewClose,
  });
  const {
    canShowEntityMergeReview,
    canShowKnowledgeGraph,
    closeGraphForFilePreview,
    closeKnowledgeGraph,
    collapsedTimelineGroups,
    collapseAllTimelineGroups,
    entityMergeCandidates,
    entityMergeLoading,
    entityMergeMessage,
    entityMergePreview,
    expandAllTimelineGroups,
    graphEntityFilter,
    graphSearchTerm,
    graphTimelineDensity,
    graphTimelineFilter,
    handleApplyEntityMergeCandidate,
    handleLoadEntityMergeCandidates,
    handleLoadNativeGraphContext,
    handleOpenKnowledgeGraph,
    handlePreviewEntityMergeCandidate,
    knowledgeGraph,
    knowledgeGraphCanvasOpen,
    knowledgeGraphError,
    knowledgeGraphLabel,
    knowledgeGraphLoading,
    knowledgeGraphOpen,
    nativeGraphContext,
    nativeGraphLoadingSlug,
    nativeGraphMessage,
    openGraphSourcePreview,
    selectedGraphEventId,
    selectedGraphNodeId,
    setGraphEntityFilter,
    setGraphSearchTerm,
    setGraphTimelineDensity,
    setGraphTimelineFilter,
    setKnowledgeGraphCanvasOpen,
    setKnowledgeGraphError,
    setSelectedGraphEventId,
    setSelectedGraphNodeId,
    toggleTimelineGroup,
    viewModel: knowledgeGraphViewModel,
  } = useWorkspaceKnowledgeGraph({
    apiOptions,
    canIngestKnowledge,
    closeFilePreview,
    isCustomerWorkspace,
    onCustomerIntelligenceClose,
    openFilePreview,
    standaloneCustomerIntelligence,
    workspaceId,
    workspaceKind: workspaceKind as "user" | "project" | "customer",
  });

  async function openWorkspaceFilePreview(item: WorkspaceFileItemResponse) {
    closeGraphForFilePreview();
    await openFilePreview(item);
  }

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
  const showMeetingWorkflowToolbar = workspaceKind !== "user" && viewMode === "files" && (isMeetingRoot || hasMeetingWorkflowDirs);
  const isLegitimateMeetingFolder = isMeetingFolderPath(currentPath);
  const activeMeetingFolderPath = isLegitimateMeetingFolder ? MEETING_ROOT_PATH : currentPath;
  const {
    canCopyWorkspaceItem,
    canModifyWorkspaceItem,
    canMoveItemTo,
    canPasteInto,
    clipboardItem,
    downloadWorkspaceFile,
    executeMove,
    handleClearTrash,
    handleCopy,
    handleCreateFolder,
    handleCut,
    handleDelete,
    handlePaste,
    handlePermanentDelete,
    handleRefreshKnowledge,
    handleRename,
    handleRestore,
    handleTextPromptSubmit,
    handleUpload,
    setTextPrompt,
    setTextPromptValue,
    textPrompt,
    textPromptBusy,
    textPromptValue,
    uploadProgress,
  } = useWorkspaceFileActions({
    activePreviewPath: filePreview?.item.path,
    apiOptions,
    closeFilePreview,
    currentPath,
    fileInputRef,
    navigateTo,
    pendingIngestCount,
    refresh,
    setError,
    setLatestAgentRun,
    setNotice,
    setPendingConfirmation,
    setRefreshingKnowledge,
    workspaceId,
    workspaceKind,
  });
  const {
    detectedSpeakers,
    handleGenerateMinutes,
    handleIngestMeeting,
    handleMediaTranscribe,
    handleMeetingFolderCreate,
    handleMeetingTranscriptSave,
    handleOpenSpeakerMap,
    handleRetryMeeting,
    handleSaveSpeakerMap,
    handleSaveTermCorrections,
    handleTranscriptFileSelect,
    meetingFolderForm,
    meetingTranscriptForm,
    openMeetingFolderForm,
    openMeetingTranscriptForm,
    setMeetingFolderForm,
    setMeetingTranscriptForm,
    setSpeakerMapNames,
    setSpeakerMapOpen,
    setTermCorrections,
    setTermCorrectionsOpen,
    setTermEditCorrected,
    setTermEditOriginal,
    speakerMapLoading,
    speakerMapNames,
    speakerMapOpen,
    termCorrections,
    termCorrectionsBusy,
    termCorrectionsOpen,
    termEditCorrected,
    termEditOriginal,
  } = useWorkspaceMeetingWorkflow({
    activeMeetingFolderPath,
    apiOptions,
    closeActionMenu: () => setActionMenuOpen(false),
    closeContextMenu: () => setContextMenu(null),
    currentPath,
    navigateTo,
    refresh,
    setError,
    setLatestAgentRun,
    setNotice,
    setPendingConfirmation,
    setRefreshingKnowledge,
    workspaceId,
    workspaceKind,
    workspaceName,
  });

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
    if (!latestAgentRun) {
      setAgentRunToastExpanded(false);
      setAgentRunToastLeaving(false);
      return;
    }
    setAgentRunToastLeaving(false);
    if (agentRunToastExpanded) return;
    const hideTimer = window.setTimeout(() => {
      setAgentRunToastLeaving(true);
    }, 4000);
    const removeTimer = window.setTimeout(() => {
      setLatestAgentRun(null);
      setAgentRunToastLeaving(false);
    }, 4300);
    return () => {
      window.clearTimeout(hideTimer);
      window.clearTimeout(removeTimer);
    };
  }, [latestAgentRun, agentRunToastExpanded]);

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

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel || typeof ResizeObserver === "undefined") return;
    const updateCompactState = () => {
      setCompactActions(panel.getBoundingClientRect().width <= 420);
    };
    updateCompactState();
    const observer = new ResizeObserver(updateCompactState);
    observer.observe(panel);
    return () => observer.disconnect();
  }, []);

  const hasSidecar = Boolean(!standaloneCustomerIntelligence && (filePreview || (knowledgeGraphOpen && workspaceKind !== "customer")));
  const { previewWidth, previewResizing, handlePreviewResizeStart } = useWorkspacePreviewWidth({
    hasSidecar,
    layoutRef,
    resetKey: filePreview?.item.path,
  });
  const {
    knowledgeGraphCanvasView,
    knowledgeGraphCanvasPanning,
    resetKnowledgeGraphCanvasView,
    zoomKnowledgeGraphCanvas,
    handleKnowledgeGraphCanvasWheel,
    handleKnowledgeGraphCanvasPanStart,
  } = useKnowledgeGraphCanvas();


  useEffect(() => {
    function closeFloatingMenus() {
      setActionMenuOpen(false);
      setContextMenu(null);
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") closeFloatingMenus();
    }

    document.addEventListener("click", closeFloatingMenus);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("click", closeFloatingMenus);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  function activateFileItem(item: WorkspaceFileItemResponse) {
    if (isTrashWorkspaceItem(item)) {
      setViewMode("trash");
      navigateTo("");
      return;
    }
    if (item.type === "directory") {
      navigateTo(item.path);
      return;
    }
    void openWorkspaceFilePreview(item);
  }

  function handleFileItemKeyDown(event: KeyboardEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activateFileItem(item);
  }

  async function handleConfirmAction() {
    if (!pendingConfirmation || confirmationBusy) return;
    setConfirmationBusy(true);
    setError(null);
    try {
      await pendingConfirmation.onConfirm();
      setPendingConfirmation(null);
    } catch (confirmError: unknown) {
      setError(confirmError instanceof Error ? confirmError.message : "操作失败");
    } finally {
      setConfirmationBusy(false);
    }
  }

  const {
    draggedItem,
    dropTargetPath,
    setDropTargetPath,
    handleFileDragStart,
    handleFileDragEnd,
    handleDirectoryDragOver,
    handleDirectoryDrop,
    handleDrop,
  } = useWorkspaceFileDragDrop({
    currentPath,
    canModifyWorkspaceItem,
    canMoveItemTo,
    executeMove,
    handleUpload,
    setDragOver,
  });

  function openFileContextMenu(event: MouseEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) {
    event.preventDefault();
    event.stopPropagation();
    const menuWidth = 176;
    const menuHeight = item.type === "directory" ? 230 : 260;
    const x = Math.min(event.clientX, window.innerWidth - menuWidth - 8);
    const y = Math.min(event.clientY, window.innerHeight - menuHeight - 8);
    setActionMenuOpen(false);
    setContextMenu({
      item,
      kind: "item",
      targetDirectory: item.type === "directory" ? item.path : currentPath,
      x: Math.max(8, x),
      y: Math.max(8, y),
    });
  }

  function openBlankContextMenu(event: MouseEvent<HTMLElement | HTMLDivElement>) {
    if (viewMode !== "files") return;
    const target = event.target as HTMLElement;
    if (
      target.closest(".workspace-file-row")
      || target.closest(".workspace-file-context-menu")
      || target.closest(".agent-file-panel-header")
      || target.closest(".workspace-file-breadcrumb")
      || target.closest(".workspace-confirm-card")
      || target.closest(".agent-file-panel-note")
      || target.closest("button,input,textarea,select,a")
    ) {
      return;
    }
    event.preventDefault();
    const menuWidth = 176;
    const menuHeight = 116;
    const x = Math.min(event.clientX, window.innerWidth - menuWidth - 8);
    const y = Math.min(event.clientY, window.innerHeight - menuHeight - 8);
    setActionMenuOpen(false);
    setContextMenu({
      kind: "blank",
      targetDirectory: currentPath,
      x: Math.max(8, x),
      y: Math.max(8, y),
    });
  }

  function runContextAction(action: () => void) {
    setContextMenu(null);
    action();
  }

  const panelSubtitle = viewMode === "trash" ? "回收站" : isPersonalWorkspace ? "个人文件" : isCustomerWorkspace ? "资料文件" : "项目资料";
  const rootTitle = isPersonalWorkspace ? "个人文件根目录" : isCustomerWorkspace ? "CRM 文件根目录" : "项目资料根目录";
  const canShowKnowledgeIngest = !isPersonalWorkspace && canIngestKnowledge;

  return (
    <div
      className={`workspace-file-panel-layout ${standaloneCustomerIntelligence ? "is-crm-standalone" : ""} ${hasSidecar ? "has-preview" : ""}`}
      ref={layoutRef}
      style={hasSidecar && !standaloneCustomerIntelligence ? { gridTemplateColumns: `minmax(300px, 1fr) ${previewWidth}px` } : undefined}
    >
    {!standaloneCustomerIntelligence ? (
    <>
    <section
      className={`agent-file-panel ${dragOver ? "is-drag-over" : ""} ${compactActions ? "is-compact-actions" : ""}`}
      onDragLeave={() => {
        setDragOver(false);
        setDropTargetPath(null);
      }}
      onDragOver={(event) => {
        if (draggedItem && hasWorkspaceDrag(event)) {
          if (canMoveItemTo(draggedItem, currentPath)) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            setDropTargetPath(currentPath);
          }
          return;
        }
        if (hasExternalFiles(event)) {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          setDragOver(true);
        }
      }}
      onDrop={handleDrop}
      onContextMenu={openBlankContextMenu}
      ref={panelRef}
    >
      <WorkspaceFilePanelHeader
        actionMenuOpen={actionMenuOpen}
        canPasteInto={canPasteInto}
        canShowKnowledgeGraph={canShowKnowledgeGraph}
        canShowKnowledgeIngest={canShowKnowledgeIngest}
        currentPath={currentPath}
        fileInputRef={fileInputRef}
        handleClearTrash={handleClearTrash}
        handleCreateFolder={handleCreateFolder}
        handleGenerateMinutes={handleGenerateMinutes}
        handleIngestMeeting={handleIngestMeeting}
        handleMediaTranscribe={handleMediaTranscribe}
        handleOpenKnowledgeGraph={handleOpenKnowledgeGraph}
        handleOpenSpeakerMap={handleOpenSpeakerMap}
        handleOpenTranscriptForm={() => openMeetingTranscriptForm()}
        handlePaste={handlePaste}
        handleRefreshKnowledge={handleRefreshKnowledge}
        handleUpload={handleUpload}
        isInMeetingFolder={isInMeetingFolder}
        isPersonalWorkspace={isPersonalWorkspace}
        knowledgeGraphLabel={knowledgeGraphLabel}
        knowledgeGraphLoading={knowledgeGraphLoading}
        loading={loading}
        navigateTo={navigateTo}
        panelSubtitle={panelSubtitle}
        pendingIngestCount={pendingIngestCount}
        refresh={refresh}
        refreshingKnowledge={refreshingKnowledge}
        setActionMenuOpen={setActionMenuOpen}
        setTermCorrectionsOpen={setTermCorrectionsOpen}
        setViewMode={setViewMode}
        showMeetingWorkflowToolbar={showMeetingWorkflowToolbar}
        viewMode={viewMode}
        workspaceKind={workspaceKind}
        workspaceName={workspaceName}
      />

      {viewMode === "files" || viewMode === "trash" ? (
        <WorkspaceFileBreadcrumb
          breadcrumb={breadcrumb}
          currentPath={currentPath}
          dropTargetPath={dropTargetPath}
          historyIndex={historyIndex}
          historyLength={history.length}
          isPersonalWorkspace={isPersonalWorkspace}
          rootTitle={rootTitle}
          viewMode={viewMode}
          onBack={goBack}
          onDragOverDirectory={handleDirectoryDragOver}
          onDropDirectory={handleDirectoryDrop}
          onForward={goForward}
          onNavigate={navigateTo}
          onReturnToFiles={() => { setViewMode("files"); navigateTo(""); }}
          onUp={goUp}
        />
      ) : null}

      {showMeetingWorkflowToolbar ? (
        <WorkspaceMeetingToolbar
          isLegitimateMeetingFolder={isLegitimateMeetingFolder}
          refreshing={refreshingKnowledge}
          onGenerateMinutes={() => void handleGenerateMinutes()}
          onIngestActionsOnly={() => void handleIngestMeeting(true)}
          onIngestMeeting={() => void handleIngestMeeting()}
          onMediaTranscribe={() => handleMediaTranscribe()}
          onOpenSpeakerMap={() => void handleOpenSpeakerMap()}
          onOpenTermCorrections={() => setTermCorrectionsOpen(true)}
          onOpenTranscriptForm={() => openMeetingTranscriptForm()}
          onRegenerateMinutes={() => void handleGenerateMinutes(true)}
          onRetryGenerateMinutes={() => void handleRetryMeeting("generate_minutes")}
          onRetryTranscribe={() => void handleRetryMeeting("transcribe")}
        />
      ) : null}
      {showMeetingWorkflowToolbar && isMeetingRoot && currentPath === MEETING_ROOT_PATH && !hasMeetingWorkflowDirs ? (
        <p className="agent-file-panel-note" style={{ margin: "8px 12px" }}>
          会议资料请放入 20-会议与沟通；可先上传会议音视频或保存已有转录文本。
        </p>
      ) : null}

      <WorkspaceUploadProgress progress={uploadProgress} />

      {error ? (
        <p className="agent-file-panel-note is-error">
          <span>{error}</span>
          <button onClick={() => setError(null)} type="button">关闭</button>
        </p>
      ) : null}
      {notice ? (
        <p className="agent-file-panel-note is-success">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} type="button">关闭</button>
        </p>
      ) : null}
      {pendingConfirmation ? (
        <WorkspaceConfirmationCard
          busy={confirmationBusy}
          confirmation={pendingConfirmation}
          onCancel={() => setPendingConfirmation(null)}
          onConfirm={() => void handleConfirmAction()}
        />
      ) : null}
      {loading ? <p className="agent-file-panel-note">正在读取目录...</p> : null}
      {!loading && !error && visibleItems.length === 0 ? (
        <div className="agent-file-empty">
          <strong>{viewMode === "trash" ? "回收站为空" : "这里还没有文件"}</strong>
          <span>{viewMode === "trash" ? "删除后的文件会先保留在这里。" : "拖入文件，或从顶部按钮上传/新建文件夹。"}</span>
        </div>
      ) : null}
      {!loading && visibleItems.length > 0 ? (
        viewMode === "trash" ? (
          <WorkspaceTrashTable
            items={visibleItems}
            onPermanentDelete={handlePermanentDelete}
            onRestore={handleRestore}
          />
        ) : (
          <div className="workspace-file-list" role="list">
            {visibleItems.map((item) => (
              <WorkspaceFileRow
                canDrag={canModifyWorkspaceItem(item)}
                canShowKnowledgeIngest={canShowKnowledgeIngest}
                cutPath={clipboardItem?.action === "cut" ? clipboardItem.item.path : undefined}
                dropTargetPath={dropTargetPath}
                isPersonalWorkspace={isPersonalWorkspace}
                item={item}
                key={item.path}
                selectedPath={filePreview?.item.path}
                onActivate={activateFileItem}
                onContextMenu={openFileContextMenu}
                onDragEnd={handleFileDragEnd}
                onDragOverDirectory={handleDirectoryDragOver}
                onDragStart={handleFileDragStart}
                onDropDirectory={handleDirectoryDrop}
                onKeyDown={handleFileItemKeyDown}
                onRetryKnowledge={(target) => void handleRefreshKnowledge(target.path, false, target)}
                onShowMeetingDetail={(target) => {
                  if (target.path.startsWith("20-会议与沟通")) {
                    setCurrentPath(target.path.split("/").slice(0, -1).join("/"));
                  }
                }}
              />
            ))}
          </div>
        )
      ) : null}
      {contextMenu ? (
        <WorkspaceFileContextMenu
          activateFileItem={activateFileItem}
          apiOptions={apiOptions}
          canCopyWorkspaceItem={canCopyWorkspaceItem}
          canModifyWorkspaceItem={canModifyWorkspaceItem}
          canPasteInto={canPasteInto}
          canShowKnowledgeIngest={canShowKnowledgeIngest}
          contextMenu={contextMenu}
          downloadWorkspaceFile={downloadWorkspaceFile}
          handleCopy={handleCopy}
          handleCreateFolder={handleCreateFolder}
          handleCut={handleCut}
          handleDelete={handleDelete}
          handleGenerateMinutes={handleGenerateMinutes}
          handleIngestMeeting={handleIngestMeeting}
          handlePaste={handlePaste}
          handleRefreshKnowledge={handleRefreshKnowledge}
          handleRename={handleRename}
          loading={loading}
          onReferenceFile={onReferenceFile}
          openFilePreview={openWorkspaceFilePreview}
          refresh={refresh}
          refreshingKnowledge={refreshingKnowledge}
          runContextAction={runContextAction}
          setCurrentPath={setCurrentPath}
          setError={setError}
          setLatestAgentRun={setLatestAgentRun}
          setNotice={setNotice}
          setPendingConfirmation={setPendingConfirmation}
          setRefreshingKnowledge={setRefreshingKnowledge}
          workspaceId={workspaceId}
          workspaceKind={workspaceKind}
          workspaceName={workspaceName}
        />
      ) : null}
      {textPrompt ? (
        <WorkspaceTextPromptDialog
          busy={textPromptBusy}
          prompt={textPrompt}
          value={textPromptValue}
          onCancel={() => setTextPrompt(null)}
          onChange={setTextPromptValue}
          onSubmit={() => void handleTextPromptSubmit()}
        />
      ) : null}
      {meetingFolderForm.open ? (
        <WorkspaceMeetingFolderDialog
          form={meetingFolderForm}
          setForm={setMeetingFolderForm}
          onSubmit={() => void handleMeetingFolderCreate()}
        />
      ) : null}
      {meetingTranscriptForm.open ? (
        <WorkspaceMeetingTranscriptDialog
          form={meetingTranscriptForm}
          setForm={setMeetingTranscriptForm}
          onFileSelect={handleTranscriptFileSelect}
          onSubmit={() => void handleMeetingTranscriptSave()}
        />
      ) : null}
      {termCorrectionsOpen ? (
        <WorkspaceMeetingTermCorrectionsDialog
          busy={termCorrectionsBusy}
          corrections={termCorrections}
          editCorrected={termEditCorrected}
          editOriginal={termEditOriginal}
          setCorrections={setTermCorrections}
          setEditCorrected={setTermEditCorrected}
          setEditOriginal={setTermEditOriginal}
          onClose={() => setTermCorrectionsOpen(false)}
          onSave={() => void handleSaveTermCorrections()}
        />
      ) : null}
      {speakerMapOpen ? (
        <WorkspaceMeetingSpeakerMapDialog
          loading={speakerMapLoading}
          speakers={detectedSpeakers}
          speakerNames={speakerMapNames}
          setSpeakerNames={setSpeakerMapNames}
          onClose={() => setSpeakerMapOpen(false)}
          onSave={() => void handleSaveSpeakerMap()}
        />
      ) : null}
      {dragOver ? <div className="workspace-drop-hint">松开后上传到当前文件夹</div> : null}
    </section>
    {latestAgentRun ? (
      <WorkspaceAgentRunToast
        expanded={agentRunToastExpanded}
        leaving={agentRunToastLeaving}
        run={latestAgentRun}
        onDismiss={() => setLatestAgentRun(null)}
        onToggleDetails={() => setAgentRunToastExpanded((value) => !value)}
      />
    ) : null}
    {filePreview ? (
      <WorkspaceFilePreviewSidecar
        preview={filePreview}
        resizing={previewResizing}
        onClose={closeFilePreview}
        onDownload={downloadWorkspaceFile}
        onResizeStart={handlePreviewResizeStart}
      />
    ) : null}
    </>
    ) : null}
    {isCustomerWorkspace ? (
      <WorkspaceCustomerIntelligenceOverlay
        canShowEntityMergeReview={canShowEntityMergeReview}
        closeKnowledgeGraph={closeKnowledgeGraph}
        entityMergeLoading={entityMergeLoading}
        entityMergeMessage={entityMergeMessage}
        graphEntityFilter={graphEntityFilter}
        graphSearchTerm={graphSearchTerm}
        graphTimelineFilter={graphTimelineFilter}
        handleApplyEntityMergeCandidate={handleApplyEntityMergeCandidate}
        handleLoadEntityMergeCandidates={handleLoadEntityMergeCandidates}
        handleOpenKnowledgeGraph={handleOpenKnowledgeGraph}
        handlePreviewEntityMergeCandidate={handlePreviewEntityMergeCandidate}
        knowledgeGraph={knowledgeGraph}
        knowledgeGraphError={knowledgeGraphError}
        knowledgeGraphLoading={knowledgeGraphLoading}
        knowledgeGraphOpen={knowledgeGraphOpen}
        openGraphSourcePreview={openGraphSourcePreview}
        resetKnowledgeGraphCanvasView={resetKnowledgeGraphCanvasView}
        setGraphEntityFilter={setGraphEntityFilter}
        setGraphSearchTerm={setGraphSearchTerm}
        setGraphTimelineFilter={setGraphTimelineFilter}
        setKnowledgeGraphCanvasOpen={setKnowledgeGraphCanvasOpen}
        setSelectedGraphEventId={setSelectedGraphEventId}
        setSelectedGraphNodeId={setSelectedGraphNodeId}
        selectedGraphEventId={selectedGraphEventId}
        selectedGraphNodeId={selectedGraphNodeId}
        viewModel={knowledgeGraphViewModel}
        workspaceName={workspaceName}
      />
    ) : null}
    <WorkspaceKnowledgeGraphSidecar
      canShowEntityMergeReview={canShowEntityMergeReview}
      closeKnowledgeGraph={closeKnowledgeGraph}
      collapsedTimelineGroups={collapsedTimelineGroups}
      collapseAllTimelineGroups={collapseAllTimelineGroups}
      entityMergeCandidates={entityMergeCandidates}
      entityMergeLoading={entityMergeLoading}
      entityMergeMessage={entityMergeMessage}
      entityMergePreview={entityMergePreview}
      expandAllTimelineGroups={expandAllTimelineGroups}
      filePreviewOpen={Boolean(filePreview)}
      graphEntityFilter={graphEntityFilter}
      graphSearchTerm={graphSearchTerm}
      graphTimelineDensity={graphTimelineDensity}
      graphTimelineFilter={graphTimelineFilter}
      handleApplyEntityMergeCandidate={handleApplyEntityMergeCandidate}
      handleLoadEntityMergeCandidates={handleLoadEntityMergeCandidates}
      handleLoadNativeGraphContext={handleLoadNativeGraphContext}
      handlePreviewEntityMergeCandidate={handlePreviewEntityMergeCandidate}
      handlePreviewResizeStart={handlePreviewResizeStart}
      isCustomerWorkspace={isCustomerWorkspace}
      knowledgeGraph={knowledgeGraph}
      knowledgeGraphError={knowledgeGraphError}
      knowledgeGraphLabel={knowledgeGraphLabel}
      knowledgeGraphLoading={knowledgeGraphLoading}
      knowledgeGraphOpen={knowledgeGraphOpen}
      nativeGraphContext={nativeGraphContext}
      nativeGraphLoadingSlug={nativeGraphLoadingSlug}
      nativeGraphMessage={nativeGraphMessage}
      openGraphSourcePreview={openGraphSourcePreview}
      previewResizing={previewResizing}
      resetKnowledgeGraphCanvasView={resetKnowledgeGraphCanvasView}
      selectedGraphEventId={selectedGraphEventId}
      selectedGraphNodeId={selectedGraphNodeId}
      setGraphEntityFilter={setGraphEntityFilter}
      setGraphSearchTerm={setGraphSearchTerm}
      setGraphTimelineDensity={setGraphTimelineDensity}
      setGraphTimelineFilter={setGraphTimelineFilter}
      setKnowledgeGraphCanvasOpen={setKnowledgeGraphCanvasOpen}
      setKnowledgeGraphError={setKnowledgeGraphError}
      setSelectedGraphEventId={setSelectedGraphEventId}
      setSelectedGraphNodeId={setSelectedGraphNodeId}
      standaloneCustomerIntelligence={standaloneCustomerIntelligence}
      toggleTimelineGroup={toggleTimelineGroup}
      viewModel={knowledgeGraphViewModel}
      workspaceName={workspaceName}
    />
    <WorkspaceKnowledgeMapOverlay
      graphTimelineFilter={graphTimelineFilter}
      handleKnowledgeGraphCanvasPanStart={handleKnowledgeGraphCanvasPanStart}
      handleKnowledgeGraphCanvasWheel={handleKnowledgeGraphCanvasWheel}
      isCustomerWorkspace={isCustomerWorkspace}
      knowledgeGraph={knowledgeGraph}
      knowledgeGraphCanvasOpen={knowledgeGraphCanvasOpen}
      knowledgeGraphCanvasPanning={knowledgeGraphCanvasPanning}
      knowledgeGraphCanvasView={knowledgeGraphCanvasView}
      knowledgeGraphLabel={knowledgeGraphLabel}
      openGraphSourcePreview={openGraphSourcePreview}
      resetKnowledgeGraphCanvasView={resetKnowledgeGraphCanvasView}
      setGraphTimelineFilter={setGraphTimelineFilter}
      setKnowledgeGraphCanvasOpen={setKnowledgeGraphCanvasOpen}
      setSelectedGraphEventId={setSelectedGraphEventId}
      setSelectedGraphNodeId={setSelectedGraphNodeId}
      selectedGraphNodeId={selectedGraphNodeId}
      viewModel={knowledgeGraphViewModel}
      workspaceName={workspaceName}
      zoomKnowledgeGraphCanvas={zoomKnowledgeGraphCanvas}
    />
    </div>
  );
}
