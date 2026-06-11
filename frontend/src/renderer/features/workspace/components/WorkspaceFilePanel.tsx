import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent, type WheelEvent } from "react";

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
  type WorkspaceMeetingFolderForm,
} from "./WorkspaceMeetingFolderDialog";
import {
  WorkspaceMeetingTranscriptDialog,
  type WorkspaceMeetingTranscriptForm,
} from "./WorkspaceMeetingTranscriptDialog";
import {
  clearWorkspaceTrash,
  applyWorkspaceEntityMergeCandidateAction,
  copyWorkspacePath,
  createMeetingFolder,
  createWorkspaceFolder,
  deleteWorkspaceFile,
  deleteWorkspaceFolder,
  enqueueWorkspaceKnowledgeIngest,
  fetchWorkspaceFileBlob,
  getWorkspaceEntityMergeCandidates,
  getWorkspaceEntityMergeCandidatePreview,
  getWorkspaceKnowledgeGraph,
  getWorkspaceKnowledgeIngestJob,
  getWorkspaceNativeGraphContext,
  permanentlyDeleteWorkspaceFile,
  moveWorkspacePath,
  renameWorkspacePath,
  restoreWorkspaceFile,
  listWorkspaceFiles,
  generateMeetingMinutesAndActions,
  getMeetingSpeakers,
  ingestMeetingToGBrain,
  preflightMeetingMediaTranscribe,
  retryMeetingOperation,
  saveMeetingSpeakerMap,
  saveMeetingTermCorrections,
  saveMeetingTranscript,
  transcribeMeetingMedia,
  saveMeetingTranscriptFromFile,
  uploadWorkspaceFiles,
} from "../api";
import {
  clampGraphCanvasScale,
  crmEntityLabel,
  crmRelationLabel,
  crmShortSource,
  graphCanvasLabel,
  graphCanvasLargeLabel,
  graphCitationString,
  graphEntityTypeColor,
  graphEventTimestamp,
  graphPreviewSourcePath,
  normalizeGraphSourcePath,
} from "../knowledgeGraphUtils";
import { buildWorkspaceKnowledgeGraphViewModel } from "../workspaceKnowledgeGraphViewModel";
import {
  clampPreviewWidth,
  countPendingIngestFiles,
  filterSystemWorkspaceItems,
  findDirectory,
  formatSize,
  getFileKind,
  getItemsAtPath,
  getParentPath,
  getRagStatusMeta,
  hasExternalFiles,
  hasWorkspaceDrag,
  isDirectoryInside,
  isProtectedWorkspaceDirectory,
  isTrashPath,
  isTrashWorkspaceItem,
  knowledgeStoreLabel,
  makeBreadcrumb,
  MEETING_ROOT_PATH,
  MEETING_WORKFLOW_DIRS,
  PREVIEW_DEFAULT_WIDTH,
  readPreviewWidth,
  type WorkspaceFilePreview,
  WORKSPACE_DRAG_MIME,
  writePreviewWidth,
} from "../workspaceFilePanelUtils";
import {
  inferMeetingFolder,
  isInMeetingWorkflowPath,
  isMeetingAudioFile,
  isMeetingFolderPath,
  isMeetingTranscriptSourceFile,
  isMeetingWorkflowSubdirName,
} from "../workspaceMeetingUtils";
import type { ApiClientOptions } from "../../../shared/api/client";
import type { AgentRunResponse, DetectedSpeaker, GBrainEntityMergeCandidate, GBrainEntityMergePreviewResponse, MeetingFolderResponse, MeetingGenerateResponse, MeetingRetryResponse, MediaPreflightResponse, SaveMeetingTranscriptResponse, WorkspaceEntityMergeCandidatesResponse, WorkspaceFileItemResponse, WorkspaceKnowledgeGraphResponse, WorkspaceNativeGraphContextResponse } from "../../../shared/api/types";
import { parseApiDate } from "../../../shared/utils/time";
import {
  AgentIcon,
  ArchiveIcon,
  ArrowUpIcon,
  BrainIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  EditIcon,
  MoreIcon,
  MoveIcon,
  MaximizeIcon,
  NoteIcon,
  PlusIcon,
  RefreshIcon,
  SearchIcon,
  TrashIcon,
  WorkspaceIcon,
  XmarkIcon,
} from "../../../shared/icons/LineIcons";

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

type WorkspaceFileContextMenu = {
  item?: WorkspaceFileItemResponse;
  targetDirectory: string;
  kind: "item" | "blank";
  x: number;
  y: number;
};

type WorkspaceClipboardItem = {
  action: "copy" | "cut";
  item: WorkspaceFileItemResponse;
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
  const [filePreview, setFilePreview] = useState<WorkspaceFilePreview | null>(null);
  const [knowledgeGraph, setKnowledgeGraph] = useState<WorkspaceKnowledgeGraphResponse | null>(null);
  const [knowledgeGraphOpen, setKnowledgeGraphOpen] = useState(false);
  const [knowledgeGraphCanvasOpen, setKnowledgeGraphCanvasOpen] = useState(false);
  const [knowledgeGraphCanvasView, setKnowledgeGraphCanvasView] = useState({ x: 0, y: 0, scale: 1 });
  const [knowledgeGraphCanvasPanning, setKnowledgeGraphCanvasPanning] = useState(false);
  const [knowledgeGraphLoading, setKnowledgeGraphLoading] = useState(false);
  const [knowledgeGraphError, setKnowledgeGraphError] = useState<string | null>(null);
  const [graphSearchTerm, setGraphSearchTerm] = useState("");
  const [graphEntityFilter, setGraphEntityFilter] = useState("all");
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [selectedGraphEventId, setSelectedGraphEventId] = useState<string | null>(null);
  const [graphTimelineFilter, setGraphTimelineFilter] = useState<"all" | "dated" | "undated" | "selected">("all");
  const [graphTimelineDensity, setGraphTimelineDensity] = useState<"detail" | "compact" | "axis">("detail");
  const [collapsedTimelineGroups, setCollapsedTimelineGroups] = useState<Set<string>>(() => new Set());
  const [entityMergeCandidates, setEntityMergeCandidates] = useState<WorkspaceEntityMergeCandidatesResponse | null>(null);
  const [entityMergePreview, setEntityMergePreview] = useState<GBrainEntityMergePreviewResponse | null>(null);
  const [entityMergeLoading, setEntityMergeLoading] = useState(false);
  const [entityMergeMessage, setEntityMergeMessage] = useState<string | null>(null);
  const [nativeGraphContext, setNativeGraphContext] = useState<WorkspaceNativeGraphContextResponse | null>(null);
  const [nativeGraphLoadingSlug, setNativeGraphLoadingSlug] = useState<string | null>(null);
  const [nativeGraphMessage, setNativeGraphMessage] = useState<string | null>(null);
  const [refreshingKnowledge, setRefreshingKnowledge] = useState(false);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<WorkspaceFileContextMenu | null>(null);
  const [textPrompt, setTextPrompt] = useState<WorkspaceTextPrompt | null>(null);
  const [textPromptValue, setTextPromptValue] = useState("");
  const [textPromptBusy, setTextPromptBusy] = useState(false);
  const [meetingFolderForm, setMeetingFolderForm] = useState<WorkspaceMeetingFolderForm>({ open: false, topic: "", meetingTime: "", meetingType: "其他", busy: false });
  const [meetingTranscriptForm, setMeetingTranscriptForm] = useState<WorkspaceMeetingTranscriptForm>({ open: false, folderPath: "", content: "", selectedFile: null, busy: false });
  const [speakerMapOpen, setSpeakerMapOpen] = useState(false);
  const [detectedSpeakers, setDetectedSpeakers] = useState<DetectedSpeaker[]>([]);
  const [speakerMapLoading, setSpeakerMapLoading] = useState(false);
  const [speakerMapNames, setSpeakerMapNames] = useState<Record<string, string>>({});
  const [termCorrectionsOpen, setTermCorrectionsOpen] = useState(false);
  const [termCorrections, setTermCorrections] = useState<Array<{original:string;corrected:string}>>([]);
  const [termCorrectionsBusy, setTermCorrectionsBusy] = useState(false);
  const [termEditOriginal, setTermEditOriginal] = useState("");
  const [termEditCorrected, setTermEditCorrected] = useState("");
  const [clipboardItem, setClipboardItem] = useState<WorkspaceClipboardItem | null>(null);
  const [draggedItem, setDraggedItem] = useState<WorkspaceFileItemResponse | null>(null);
  const [dropTargetPath, setDropTargetPath] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState({ active: false, current: 0, total: 0, filename: "" });
  const [compactActions, setCompactActions] = useState(false);
  const [previewWidth, setPreviewWidth] = useState(readPreviewWidth);
  const [previewResizing, setPreviewResizing] = useState(false);
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const previewObjectUrlRef = useRef<string | null>(null);
  const graphCanvasPanRef = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

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

  useEffect(() => {
    if (!standaloneCustomerIntelligence || workspaceKind !== "customer" || !workspaceId) return;
    void handleOpenKnowledgeGraph();
  }, [standaloneCustomerIntelligence, workspaceKind, workspaceId]);

  useEffect(() => {
    if (!hasSidecar) return;
    const layout = layoutRef.current;
    if (!layout || typeof ResizeObserver === "undefined") return;
    const updatePreviewWidth = () => {
      setPreviewWidth((width) => clampPreviewWidth(width, layout.getBoundingClientRect().width));
    };
    updatePreviewWidth();
    const observer = new ResizeObserver(updatePreviewWidth);
    observer.observe(layout);
    return () => observer.disconnect();
  }, [hasSidecar]);

  useEffect(() => {
    if (!hasSidecar) return;
    setPreviewWidth((width) => clampPreviewWidth(Math.max(width, PREVIEW_DEFAULT_WIDTH), layoutRef.current?.getBoundingClientRect().width));
  }, [filePreview?.item.path, hasSidecar]);

  useEffect(() => {
    writePreviewWidth(previewWidth);
  }, [previewWidth]);

  useEffect(() => {
    if (!previewResizing) return;

    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const layout = layoutRef.current;
      if (!layout) return;
      const rect = layout.getBoundingClientRect();
      setPreviewWidth(clampPreviewWidth(rect.right - event.clientX, rect.width));
    }

    function handleMouseUp() {
      setPreviewResizing(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [previewResizing]);

  useEffect(() => {
    if (!knowledgeGraphCanvasPanning) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "grabbing";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const drag = graphCanvasPanRef.current;
      if (!drag) return;
      setKnowledgeGraphCanvasView((view) => ({
        ...view,
        x: drag.originX + (event.clientX - drag.startX) / Math.max(0.7, view.scale),
        y: drag.originY + (event.clientY - drag.startY) / Math.max(0.7, view.scale),
      }));
    }

    function handleMouseUp() {
      graphCanvasPanRef.current = null;
      setKnowledgeGraphCanvasPanning(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [knowledgeGraphCanvasPanning]);

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

  useEffect(() => {
    return () => {
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
        previewObjectUrlRef.current = null;
      }
    };
  }, []);

  async function handleUpload(fileList: FileList | File[] | null, directory = currentPath) {
    const files = Array.from(fileList ?? []);
    if (!workspaceId || files.length === 0) return;
    if (isTrashPath(directory)) {
      setError("回收站不能直接上传文件");
      return;
    }
    setError(null);
    setNotice(null);
    setUploadProgress({ active: true, current: 0, total: files.length, filename: files[0]?.name ?? "" });
    try {
      const response = await uploadWorkspaceFiles(apiOptions, workspaceId, directory, files);
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setUploadProgress({ active: true, current: files.length, total: files.length, filename: files[files.length - 1]?.name ?? "" });
      await refresh();
    } catch (uploadError: unknown) {
      setError(uploadError instanceof Error ? uploadError.message : "上传失败");
    } finally {
      window.setTimeout(() => setUploadProgress({ active: false, current: 0, total: 0, filename: "" }), 350);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function openTextPrompt(prompt: WorkspaceTextPrompt) {
    setTextPrompt(prompt);
    setTextPromptValue(prompt.initialValue);
    setTextPromptBusy(false);
  }

  async function handleTextPromptSubmit() {
    if (!textPrompt || textPromptBusy) return;
    const value = textPromptValue.trim();
    if (!value) return;
    setTextPromptBusy(true);
    setError(null);
    try {
      await textPrompt.onConfirm(value);
      setTextPrompt(null);
      setTextPromptValue("");
    } catch (promptError: unknown) {
      setError(promptError instanceof Error ? promptError.message : "操作失败");
    } finally {
      setTextPromptBusy(false);
    }
  }

  function handleCreateFolder(parentPath = currentPath) {
    if (!workspaceId) return;
    if (isTrashPath(parentPath)) {
      setError("回收站不能新建文件夹");
      return;
    }
    openTextPrompt({
      title: "新建文件夹",
      label: parentPath ? `位置：${parentPath}` : "位置：根目录",
      initialValue: "",
      confirmLabel: "新建",
      onConfirm: async (name) => {
        const response = await createWorkspaceFolder(apiOptions, workspaceId, { parent_path: parentPath, name });
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
  }

  // ── Meeting operations ──────────────────────────────────────────────────

  function openMeetingFolderForm() {
    if (!workspaceId) return;
    if (workspaceKind === "user") return;
    setMeetingFolderForm({ open: true, topic: "", meetingTime: "", meetingType: "其他", busy: false });
    setContextMenu(null);
  }

  async function handleMeetingFolderCreate() {
    if (!workspaceId || meetingFolderForm.busy) return;
    const topic = meetingFolderForm.topic.trim();
    if (!topic) return;
    setMeetingFolderForm((prev) => ({ ...prev, busy: true }));
    setError(null);
    try {
      const data: { topic: string; meeting_time?: string; meeting_type?: string } = { topic, meeting_type: meetingFolderForm.meetingType };
      if (meetingFolderForm.meetingTime.trim()) {
        data.meeting_time = meetingFolderForm.meetingTime.trim();
      }
      const response: MeetingFolderResponse = await createMeetingFolder(apiOptions, workspaceId, data);
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`已创建会议文件夹：${response.meeting_folder_path}`);
      setMeetingFolderForm({ open: false, topic: "", meetingTime: "", meetingType: "其他", busy: false });
      await refresh();
      // Navigate into the new folder
      navigateTo(response.meeting_folder_path);
    } catch (folderError: unknown) {
      setError(folderError instanceof Error ? folderError.message : "创建会议文件夹失败");
    } finally {
      setMeetingFolderForm((prev) => ({ ...prev, busy: false }));
    }
  }

  function openMeetingTranscriptForm(folderPath?: string) {
    if (!workspaceId) return;
    if (workspaceKind === "user") return;
    setMeetingTranscriptForm({
      open: true,
      folderPath: folderPath ?? activeMeetingFolderPath,
      content: "",
      selectedFile: null,
      busy: false,
    });
    setContextMenu(null);
  }

  function handleTranscriptFileSelect(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".txt") && !lower.endsWith(".md") && !lower.endsWith(".markdown") && !lower.endsWith(".docx")) {
      setError("仅支持 TXT / MD / DOCX 格式");
      return;
    }
    setMeetingTranscriptForm((prev) => ({ ...prev, selectedFile: file, content: "" }));
    // For TXT/MD, read content client-side to preview
    if (!lower.endsWith(".docx")) {
      const reader = new FileReader();
      reader.onload = () => {
        setMeetingTranscriptForm((prev) => ({
          ...prev,
          content: typeof reader.result === "string" ? reader.result : "",
        }));
      };
      reader.readAsText(file);
    }
  }

  async function handleMeetingTranscriptSave() {
    if (!workspaceId || meetingTranscriptForm.busy) return;
    const folderPath = meetingTranscriptForm.folderPath.trim();
    if (!folderPath) return;

    const hasFile = meetingTranscriptForm.selectedFile !== null;
    const content = meetingTranscriptForm.content.trim();
    if (!hasFile && !content) return;

    setMeetingTranscriptForm((prev) => ({ ...prev, busy: true }));
    setError(null);
    try {
      let response: SaveMeetingTranscriptResponse;

      if (hasFile && meetingTranscriptForm.selectedFile!.name.toLowerCase().endsWith(".docx")) {
        // DOCX: server-side extraction via file upload endpoint
        response = await saveMeetingTranscriptFromFile(
          apiOptions, workspaceId, folderPath, meetingTranscriptForm.selectedFile!,
        );
      } else if (hasFile) {
        // TXT/MD: already read client-side, submit as content
        const filename = meetingTranscriptForm.selectedFile!.name;
        const inputType = filename.toLowerCase().endsWith(".md") ? "md" : "txt";
        response = await saveMeetingTranscript(apiOptions, workspaceId, {
          folder_path: folderPath,
          content,
          input_type: inputType,
          original_filename: filename,
        });
      } else {
        // Paste
        response = await saveMeetingTranscript(apiOptions, workspaceId, {
          folder_path: folderPath,
          content,
          input_type: "paste",
        });
      }

      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`转录已保存：${response.transcript_latest_path}`);
      setMeetingTranscriptForm({ open: false, folderPath: "", content: "", selectedFile: null, busy: false });
      await refresh();
    } catch (transcriptError: unknown) {
      setError(transcriptError instanceof Error ? transcriptError.message : "保存转录失败");
    } finally {
      setMeetingTranscriptForm((prev) => ({ ...prev, busy: false }));
    }
  }

  async function handleGenerateMinutes(regenerate = false) {
    if (!workspaceId || !currentPath) return;
    if (workspaceKind === "user") return;
    const folderPath = activeMeetingFolderPath;
    setNotice("正在生成纪要与行动项...");
    setError(null);
    setRefreshingKnowledge(true);
    try {
      const response: MeetingGenerateResponse = await generateMeetingMinutesAndActions(
        apiOptions,
        workspaceId,
        { folder_path: folderPath, regenerate },
      );
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      const details = [
        `纪要：${response.minutes_latest_path}`,
        `行动项：${response.actions_latest_path}`,
      ];
      if (response.model_used === "template-fallback") {
        setNotice(`纪要与行动项已保存（LLM 暂不可用，使用模板占位）。${details.join("；")}。`);
      } else {
        setNotice(`纪要与行动项已保存（${details.join("；")}，模型：${response.model_used}，token：${response.token_cost}）。可在文件面板中下载。`);
      }
      await refresh();
    } catch (genError: unknown) {
      if (genError instanceof Error && genError.message.includes("已存在纪要与行动项")) {
        // Offer to regenerate
        setActionMenuOpen(false);
        setPendingConfirmation({
          title: "已存在纪要与行动项",
          detail: "当前会议已有纪要与行动项。重新生成将创建新版本（v2/v3…）并更新 latest。是否继续？",
          confirmLabel: "重新生成",
          tone: "warning",
          onConfirm: async () => {
            await handleGenerateMinutes(true);
          },
        });
        return;
      }
      setError(genError instanceof Error ? genError.message : "生成纪要与行动项失败");
    } finally {
      setRefreshingKnowledge(false);
    }
  }

  async function handleOpenSpeakerMap() {
    if (!workspaceId || !currentPath) return;
    setSpeakerMapOpen(true);
    setSpeakerMapLoading(true);
    setDetectedSpeakers([]);
    setError(null);
    try {
      const response = await getMeetingSpeakers(apiOptions, workspaceId, activeMeetingFolderPath);
      const speakers = response.detected_speakers ?? [];
      setDetectedSpeakers(speakers);
      // Initialize name map with detected display names
      const nameMap: Record<string, string> = {};
      for (const sp of speakers) {
        nameMap[sp.speaker_id] = sp.display_name;
      }
      setSpeakerMapNames(nameMap);
    } catch (speakerError: unknown) {
      setError(speakerError instanceof Error ? speakerError.message : "获取说话人信息失败");
      setSpeakerMapOpen(false);
    } finally {
      setSpeakerMapLoading(false);
    }
  }

  async function handleSaveSpeakerMap() {
    if (!workspaceId || !currentPath) return;
    setSpeakerMapLoading(true);
    setError(null);
    try {
      const speakers = detectedSpeakers.map((sp) => ({
        speaker_id: sp.speaker_id,
        display_name: speakerMapNames[sp.speaker_id] ?? sp.display_name,
      }));
      await saveMeetingSpeakerMap(apiOptions, workspaceId, {
        folder_path: activeMeetingFolderPath,
        speakers,
      });
      setNotice("说话人映射已保存。点击「应用修正并重跑纪要」可更新纪要。");
      setSpeakerMapOpen(false);
      await refresh();
    } catch (mapError: unknown) {
      setError(mapError instanceof Error ? mapError.message : "保存说话人映射失败");
    } finally {
      setSpeakerMapLoading(false);
    }
  }

  async function handleSaveTermCorrections() {
    if (!workspaceId || !currentPath) return;
    setTermCorrectionsBusy(true);
    setError(null);
    try {
      await saveMeetingTermCorrections(apiOptions, workspaceId, {
        folder_path: activeMeetingFolderPath,
        corrections: termCorrections,
      });
      setNotice("术语纠错已保存。");
      setTermCorrectionsOpen(false);
      setTermCorrections([]);
      await refresh();
    } catch (termErr: unknown) {
      setError(termErr instanceof Error ? termErr.message : "保存术语纠错失败");
    } finally {
      setTermCorrectionsBusy(false);
    }
  }

  async function handleIngestMeeting(actionsOnly = false) {
    if (!workspaceId || !currentPath) return;
    const sourceScope = workspaceKind === "customer" ? "CRM 客户情报" : "项目知识库";
    const scopeLabel = workspaceKind === "customer" ? "客户情报" : "当前项目";
    const detailLines = [
      `当前工作区：${workspaceName ?? workspaceKind}`,
      `目标 source：${sourceScope}（${scopeLabel}）`,
      `路径：${activeMeetingFolderPath}`,
    ];
    if (actionsOnly) {
      detailLines.push("范围：仅录入行动项文件 actions-latest.md");
      detailLines.push("将标记为「仅行动项」，低上下文完整度");
      detailLines.push("建议：如需要完整会议知识，请改为录入完整会议（纪要和转录）。");
    } else {
      detailLines.push("将取 latest 版本组合成 GBrain-ready 页面，旧版本标记为已取代。");
      detailLines.push("生成后需在 GBrain 管理端同步（本操作不自动触发 sync）。");
    }
    detailLines.push("原始音视频不直接录入。");
    detailLines.push("仅工作区管理员可操作。");

    setPendingConfirmation({
      title: actionsOnly ? "录入行动项（仅行动项）" : "录入此会议",
      detail: detailLines.join("\\n"),
      confirmLabel: "确认录入",
      tone: "warning",
      onConfirm: async () => {
        setRefreshingKnowledge(true);
        setError(null);
        try {
          const ingestData: { folder_path: string; recursive?: boolean; single_file_path?: string } = {
            folder_path: activeMeetingFolderPath,
          };
          if (actionsOnly) {
            ingestData.single_file_path = `${activeMeetingFolderPath}/05-行动项/actions-latest.md`;
          }
          const resp = await ingestMeetingToGBrain(apiOptions, workspaceId!, ingestData);
          const msgs = [`已录入 ${resp.ingested_files.length} 个文件`];
          if (resp.skipped_files.length > 0) {
            msgs.push(`跳过 ${resp.skipped_files.length} 个旧版本`);
          }
          msgs.push(`source：${resp.source_id}`);
          if (resp.warning) {
            msgs.push(`注意：${resp.warning}`);
          }
          setNotice(msgs.join("，"));
          if (resp.agent_run) setLatestAgentRun(resp.agent_run);
          await refresh();
        } catch (ingestErr: unknown) {
          setError(ingestErr instanceof Error ? ingestErr.message : "录入失败");
        } finally {
          setRefreshingKnowledge(false);
        }
      },
    });
  }

  function niceSaveSummary(filePath: string, status: string) {
    const statusLabel = status === "failed" ? "失败" : status === "partial" ? "部分完成" : "完成";
    setNotice(`已保存：${filePath}（${statusLabel}）。可下载或在文件面板查看。`);
  }

  async function handleRetryMeeting(operation: "transcribe" | "generate_minutes") {
    if (!workspaceId || !currentPath) return;
    setRefreshingKnowledge(true);
    setError(null);
    try {
      const resp: MeetingRetryResponse = await retryMeetingOperation(apiOptions, workspaceId!, {
        folder_path: activeMeetingFolderPath,
        operation,
      });
      if (resp.agent_run) setLatestAgentRun(resp.agent_run);
      setNotice(`重试完成：${resp.message}`);
      await refresh();
    } catch (retryErr: unknown) {
      setError(retryErr instanceof Error ? retryErr.message : "重试失败");
    } finally {
      setRefreshingKnowledge(false);
    }
  }

  function handleMediaTranscribe() {
    if (!workspaceId || !currentPath) return;
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".mp3,.wav,.m4a,.ogg,.flac,.mp4,.mov,.avi,.wmv,.mkv,.webm";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const sizeMB = file.size / (1024 * 1024);
      const isVideo = !!file.name.match(/\.(mp4|mov|avi|wmv|mkv|webm)$/i);

      // Attempt preflight for accurate duration estimate
      let preflight: MediaPreflightResponse | null = null;
      try {
        preflight = await preflightMeetingMediaTranscribe(apiOptions, workspaceId!, {
          folder_path: activeMeetingFolderPath,
          filename: file.name,
          size_bytes: file.size,
          content_type: file.type,
        });
      } catch {
        // Preflight unavailable; fall back to rough estimate
      }

      const estMin = preflight?.estimated_duration_minutes
        ?? (isVideo ? Math.max(1, Math.round(sizeMB / 8)) : Math.max(1, Math.round(sizeMB)));
      const estSeg = preflight?.estimated_segments ?? Math.max(1, Math.ceil(estMin / 5));
      const isLong = preflight?.is_long_media ?? (estMin > 30);

      const details: string[] = [
        `当前工作区：${workspaceName ?? workspaceKind}`,
        `目标路径：${activeMeetingFolderPath}`,
        `文件：${file.name}`,
        `大小：${sizeMB.toFixed(1)} MB`,
        `预估时长：约 ${estMin} 分钟`,
      ];

      if (isLong) {
        details.push("");
        details.push("⚠️ 高成本 / 长时间操作提示：");
        details.push(`- 预估分段数：${estSeg} 段（每段约 300 秒）`);
        details.push("- 转录模型：MiMo V2.5（语音识别 + 结构化提炼）");
        details.push(`- 长${isVideo ? "视频" : "音频"}处理预计耗时较长，请耐心等待`);
        details.push("- 处理期间请勿重复操作，完成后会收到通知");
        if (sizeMB > 500) {
          details.push("- 文件超过 500 MB，建议在网络稳定、有充裕时间时处理");
        }
      } else {
        details.push(`- 预估分段数：${estSeg} 段`);
        details.push(`- 短${isVideo ? "视频" : "音频"}，预计较快完成转录`);
      }
      details.push("");
      details.push("转录完成后将在当前文件夹的 02-转录文本 / 子目录生成结果。");

      setPendingConfirmation({
        title: isLong ? "上传并转录音视频（高成本操作）" : "上传并转录音视频",
        detail: details.join("\\n"),
        confirmLabel: "确认转录",
        tone: isLong ? "danger" : "warning",
        onConfirm: async () => {
          const folderPath = activeMeetingFolderPath;
          setNotice("正在转录音视频…");
          setRefreshingKnowledge(true);
          setError(null);
          try {
            const resp = await transcribeMeetingMedia(apiOptions, workspaceId!, folderPath, file);
            if (resp.agent_run) setLatestAgentRun(resp.agent_run);
            const notices: string[] = [];
            if (resp.transcription_status === "failed") {
              notices.push("转录失败 — 可点击「重试转录」再次尝试");
            } else if (resp.transcription_status === "partial") {
              notices.push(`部分转录完成（${resp.segment_count}段）— 可重试失败片段`);
            } else {
              notices.push(`转录完成（${resp.segment_count}段）`);
            }
            if (resp.warnings.length > 0) {
              notices.push(`${resp.warnings.length} 条警告`);
            }
            if (resp.token_cost > 0) {
              notices.push(`token：${resp.token_cost}`);
            }
            niceSaveSummary(resp.transcript_latest_path, resp.transcription_status);
            setNotice(notices.join("，"));
            await refresh();
          } catch (txErr: unknown) {
            setError(txErr instanceof Error ? txErr.message : "转录失败");
          } finally {
            setRefreshingKnowledge(false);
          }
        },
      });
    };
    input.click();
  }

  function handleRename(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    if (!canModifyWorkspaceItem(item)) {
      setError("只有上传人或管理员可以修改该文件");
      return;
    }
    openTextPrompt({
      title: "重命名",
      label: item.path,
      initialValue: item.name,
      confirmLabel: "保存",
      onConfirm: async (name) => {
        if (name === item.name) return;
        const response = await renameWorkspacePath(apiOptions, workspaceId, { path: item.path, new_name: name });
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
  }

  async function executeMove(item: WorkspaceFileItemResponse, targetDirectory: string) {
    if (!workspaceId) return;
    if (!canModifyWorkspaceItem(item)) {
      setError("只有上传人或管理员可以修改该文件");
      return;
    }
    if (!canMoveItemTo(item, targetDirectory)) return;
    try {
      const response = await moveWorkspacePath(apiOptions, workspaceId, { path: item.path, target_directory: targetDirectory, conflict_strategy: "keep_both" });
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`已移动「${item.name}」。`);
      if (filePreview?.item.path === item.path) closeFilePreview();
      await refresh();
    } catch (moveError: unknown) {
      setError(moveError instanceof Error ? moveError.message : "移动失败");
    }
  }

  async function executeCopy(item: WorkspaceFileItemResponse, targetDirectory: string) {
    if (!workspaceId) return;
    if (!canCopyWorkspaceItem(item)) {
      setError("默认项目目录不能复制");
      return;
    }
    try {
      const response = await copyWorkspacePath(apiOptions, workspaceId, { path: item.path, target_directory: targetDirectory, conflict_strategy: "keep_both" });
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`已复制「${item.name}」。`);
      await refresh();
    } catch (copyError: unknown) {
      setError(copyError instanceof Error ? copyError.message : "复制失败");
    }
  }

  function handleCut(item: WorkspaceFileItemResponse) {
    if (!canModifyWorkspaceItem(item)) {
      setError("只有上传人或管理员可以修改该文件");
      return;
    }
    setClipboardItem({ action: "cut", item });
    setNotice(`已剪切「${item.name}」，请选择目标文件夹后粘贴。`);
  }

  function handleCopy(item: WorkspaceFileItemResponse) {
    if (!canCopyWorkspaceItem(item)) {
      setError("默认项目目录不能复制");
      return;
    }
    setClipboardItem({ action: "copy", item });
    setNotice(`已复制「${item.name}」，请选择目标文件夹后粘贴。`);
  }

  async function handlePaste(targetDirectory = currentPath) {
    if (!clipboardItem) return;
    if (isTrashPath(targetDirectory)) {
      setError("回收站不能作为粘贴目标");
      return;
    }
    if (clipboardItem.action === "cut") {
      await executeMove(clipboardItem.item, targetDirectory);
      setClipboardItem(null);
      return;
    }
    await executeCopy(clipboardItem.item, targetDirectory);
  }

  async function handleDelete(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    if (!item.can_delete && item.type !== "directory") {
      setError("只有上传人或管理员可以删除该文件");
      return;
    }
    setPendingConfirmation({
      title: item.type === "directory" ? "删除项目文件夹" : "移入项目回收区",
      detail: item.type === "directory" ? `将删除空文件夹「${item.name}」。` : `将「${item.name}」移入回收区，项目知识状态会重新标记为待录入。`,
      confirmLabel: item.type === "directory" ? "删除文件夹" : "移入回收区",
      tone: "warning",
      onConfirm: async () => {
        if (item.type === "directory") {
          const response = await deleteWorkspaceFolder(apiOptions, workspaceId, item.path);
          if (response.agent_run) setLatestAgentRun(response.agent_run);
          if (currentPath.startsWith(`${item.path}/`)) navigateTo("");
        } else {
          const response = await deleteWorkspaceFile(apiOptions, workspaceId, item.path);
          if (response.agent_run) setLatestAgentRun(response.agent_run);
        }
        await refresh();
      },
    });
  }

  async function handleRestore(item: WorkspaceFileItemResponse) {
    if (!workspaceId || !item.id) return;
    try {
      const response = await restoreWorkspaceFile(apiOptions, workspaceId, item.id);
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      await refresh();
    } catch (restoreError: unknown) {
      setError(restoreError instanceof Error ? restoreError.message : "恢复失败");
    }
  }

  async function handlePermanentDelete(item: WorkspaceFileItemResponse) {
    if (!workspaceId || !item.id) return;
    setPendingConfirmation({
      title: "永久删除项目文件",
      detail: `将永久删除「${item.name}」。此操作不可恢复，且会触发项目知识状态重新计算。`,
      confirmLabel: "永久删除",
      tone: "danger",
      onConfirm: async () => {
        const response = await permanentlyDeleteWorkspaceFile(apiOptions, workspaceId, item.id!);
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
  }

  async function runKnowledgeIngest(path: string, recursive: boolean) {
    if (!workspaceId) return;
    const storeLabel = knowledgeStoreLabel(workspaceKind);
    setRefreshingKnowledge(true);
    setError(null);
    setNotice(null);
    try {
      const queued = await enqueueWorkspaceKnowledgeIngest(apiOptions, workspaceId, { path, recursive });
      setLatestAgentRun(queued.agent_run ?? null);
      setNotice(`${storeLabel}录入已进入后台队列：任务 #${queued.id}。`);
      let job = queued;
      for (let attempt = 0; attempt < 120 && ["queued", "running"].includes(job.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        job = await getWorkspaceKnowledgeIngestJob(apiOptions, workspaceId, queued.id);
        if (job.agent_run) setLatestAgentRun(job.agent_run);
      }
      if (["queued", "running"].includes(job.status)) {
        setNotice(`${storeLabel}录入仍在后台执行：任务 #${queued.id}，完成后会通知你。`);
        return;
      }
      const result = job.result;
      if (job.agent_run) setLatestAgentRun(job.agent_run);
      if (!result.ok) {
        const detail = job.error_message || result.gbrain_error || result.gbrain_status || "工作区资料已处理，但 GBrain source 尚未完成同步";
        setError(`录入未完成：${detail}`);
      } else {
        const parts = [
          `已入库 ${result.indexed_files ?? 0} 个`,
          `待能力补齐 ${result.pending_extractor_capability_files ?? 0} 个`,
          `待转写 ${result.pending_transcription_files ?? 0} 个`,
        ];
        if ((result.failed_files ?? 0) > 0) parts.push(`失败 ${result.failed_files} 个`);
        setNotice(`${storeLabel}录入完成：${parts.join("，")}。`);
      }
      await refresh();
    } catch (refreshError: unknown) {
      setError(refreshError instanceof Error ? refreshError.message : `录入${storeLabel}失败`);
    } finally {
      setRefreshingKnowledge(false);
    }
  }

  function handleRefreshKnowledge(path = currentPath, recursive = true, item?: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    const targetType = item?.type === "file" ? "file" : "directory";
    const pendingCount = item ? countPendingIngestFiles([item]) : pendingIngestCount;
    const pathLabel = path ? `「${path}」` : "当前文件夹";
    if (recursive || targetType === "directory") {
      setPendingConfirmation({
        title: targetType === "file" ? "录入此文件" : "递归录入当前文件夹",
        detail: [
          `路径：${pathLabel}`,
          targetType === "file" ? "范围：仅此文件" : `范围：递归包含子文件夹，当前可处理文件约 ${pendingCount} 个`,
          "可能调用高成本模型、转写或视觉提炼能力；不支持的文件会标记为待能力补齐。",
        ].join("；"),
        confirmLabel: targetType === "file" ? "录入此文件" : "确认录入",
        tone: "warning",
        onConfirm: () => runKnowledgeIngest(path, targetType === "file" ? false : recursive),
      });
      return;
    }
    void runKnowledgeIngest(path, false);
  }

  async function handleClearTrash() {
    if (!workspaceId) return;
    setPendingConfirmation({
      title: "清空项目回收区",
      detail: "将永久删除当前可清理的回收区文件。此操作不可恢复。",
      confirmLabel: "清空回收区",
      tone: "danger",
      onConfirm: async () => {
        const response = await clearWorkspaceTrash(apiOptions, workspaceId);
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
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

  function closeFilePreview() {
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    setFilePreview(null);
    onPreviewClose?.();
  }

  async function openFilePreview(item: WorkspaceFileItemResponse) {
    if (!workspaceId || item.type === "directory") return;
    onPreviewOpen?.();
    setKnowledgeGraphOpen(false);
    setKnowledgeGraphCanvasOpen(false);
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    const kind = getFileKind(item.name);
    setFilePreview({ item, kind, status: "loading" });
    try {
      const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
      if (kind === "image" || kind === "pdf") {
        const objectUrl = URL.createObjectURL(blob);
        previewObjectUrlRef.current = objectUrl;
        setFilePreview({ item, kind, status: "ready", objectUrl });
        return;
      }
      if (kind === "code" || item.name.toLowerCase().endsWith(".txt") || item.name.toLowerCase().endsWith(".md")) {
        const text = await blob.text();
        setFilePreview({ item, kind, status: "ready", text: text.slice(0, 60_000) });
        return;
      }
      const objectUrl = URL.createObjectURL(blob);
      previewObjectUrlRef.current = objectUrl;
      setFilePreview({ item, kind, status: "ready", objectUrl });
    } catch (previewError: unknown) {
      setFilePreview({
        item,
        kind,
        status: "failed",
        error: previewError instanceof Error ? previewError.message : "文件预览失败",
      });
    }
  }

  async function downloadWorkspaceFile(item: WorkspaceFileItemResponse) {
    if (!workspaceId || item.type === "directory") return;
    setError(null);
    try {
      const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = item.name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setNotice(`已开始下载：${item.name}`);
    } catch (downloadError: unknown) {
      setError(downloadError instanceof Error ? downloadError.message : "文件下载失败");
    }
  }

  async function openGraphSourcePreview(sourcePath: string) {
    const normalized = normalizeGraphSourcePath(sourcePath);
    if (!normalized) {
      setNativeGraphMessage("该 citation 未指向可直接预览的工作区源文件。");
      return;
    }
    const name = normalized.split("/").filter(Boolean).pop() || normalized;
    await openFilePreview({
      id: null,
      name,
      path: normalized,
      type: "file",
      size: null,
      updated_at: null,
      uploaded_by: null,
      uploader_name: null,
      deleted_at: null,
      deleted_by: null,
      rag_status: null,
      can_delete: false,
      can_restore: false,
      children: [],
    });
  }

  function handlePreviewResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setPreviewResizing(true);
  }

  async function handleOpenKnowledgeGraph() {
    if (!workspaceId) return;
    closeFilePreview();
    setKnowledgeGraphOpen(true);
    setKnowledgeGraphLoading(true);
    setKnowledgeGraphError(null);
    try {
      const result = await getWorkspaceKnowledgeGraph(apiOptions, workspaceId, { limit: 120 });
      setKnowledgeGraph(result);
      setSelectedGraphNodeId((current) => {
        if (current && result.nodes.some((node) => node.id === current)) return current;
        return result.profile_cards[0]?.id || result.nodes[0]?.id || null;
      });
      setSelectedGraphEventId((current) => {
        if (current && result.events.some((event) => event.id === current)) return current;
        return null;
      });
    } catch (graphError: unknown) {
      setKnowledgeGraphError(graphError instanceof Error ? graphError.message : "无法加载工作区图谱");
    } finally {
      setKnowledgeGraphLoading(false);
    }
  }

  async function handleLoadEntityMergeCandidates() {
    if (!workspaceId) return;
    setEntityMergeLoading(true);
    setEntityMergeMessage(null);
    try {
      const result = await getWorkspaceEntityMergeCandidates(apiOptions, workspaceId, { limit: 80 });
      setEntityMergeCandidates(result);
      const warning = result.warnings?.find((item) => item.trim());
      setEntityMergeMessage(result.ok ? "实体候选已加载。" : warning || "实体候选加载失败。");
    } catch (candidateError: unknown) {
      setEntityMergeMessage(candidateError instanceof Error ? candidateError.message : "实体候选加载失败");
    } finally {
      setEntityMergeLoading(false);
    }
  }

  async function handleApplyEntityMergeCandidate(candidate: GBrainEntityMergeCandidate, action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes") {
    if (!workspaceId) return;
    setEntityMergeLoading(true);
    setEntityMergeMessage(
      action === "dismiss"
        ? "正在忽略实体候选..."
        : action === "record_alias"
          ? "正在记录实体别名..."
          : action === "apply_relink_changes"
            ? "正在应用引用改写..."
            : "正在创建实体占位页...",
    );
    try {
      const result = await applyWorkspaceEntityMergeCandidateAction(apiOptions, workspaceId, {
        candidate_id: candidate.id,
        action,
      });
      const syncStatus = result.sync?.status ? `，sync=${result.sync.status}` : "";
      setEntityMergeMessage(result.ok ? `实体候选已处理：${result.status}${result.created_file ? `，${result.created_file}` : ""}${syncStatus}。` : result.error || "实体候选处理失败。");
      const refreshed = await getWorkspaceEntityMergeCandidates(apiOptions, workspaceId, { limit: 80 });
      setEntityMergeCandidates(refreshed);
      const graph = await getWorkspaceKnowledgeGraph(apiOptions, workspaceId, { limit: 120 });
      setKnowledgeGraph(graph);
    } catch (candidateError: unknown) {
      setEntityMergeMessage(candidateError instanceof Error ? candidateError.message : "实体候选处理失败");
    } finally {
      setEntityMergeLoading(false);
    }
  }

  async function handlePreviewEntityMergeCandidate(candidate: GBrainEntityMergeCandidate) {
    if (!workspaceId) return;
    setEntityMergeLoading(true);
    setEntityMergeMessage("正在生成实体合并预览...");
    try {
      const result = await getWorkspaceEntityMergeCandidatePreview(apiOptions, workspaceId, candidate.id);
      setEntityMergePreview(result);
      setEntityMergeMessage(`预览已生成：${result.stats?.planned_relink_changes ?? 0} 条引用建议。`);
    } catch (candidateError: unknown) {
      setEntityMergeMessage(candidateError instanceof Error ? candidateError.message : "实体合并预览失败");
    } finally {
      setEntityMergeLoading(false);
    }
  }

  async function handleLoadNativeGraphContext(slug: string) {
    if (!workspaceId || !slug) return;
    setNativeGraphLoadingSlug(slug);
    setNativeGraphMessage(null);
    try {
      const result = await getWorkspaceNativeGraphContext(apiOptions, workspaceId, {
        slug,
        depth: 2,
        direction: "both",
      });
      setSelectedGraphNodeId(slug);
      setNativeGraphContext(result);
      setNativeGraphMessage(result.status === "ok" ? (isCustomerWorkspace ? "客户情报支撑信息已加载。" : "GBrain 原生图谱上下文已加载。") : result.error || (isCustomerWorkspace ? "客户情报支撑信息加载失败。" : "GBrain 原生图谱上下文加载失败。"));
    } catch (nativeError: unknown) {
      setNativeGraphMessage(nativeError instanceof Error ? nativeError.message : (isCustomerWorkspace ? "客户情报支撑信息加载失败" : "GBrain 原生图谱上下文加载失败"));
    } finally {
      setNativeGraphLoadingSlug(null);
    }
  }

  function closeKnowledgeGraph() {
    setKnowledgeGraphOpen(false);
    setKnowledgeGraphCanvasOpen(false);
    onCustomerIntelligenceClose?.();
  }

  function resetKnowledgeGraphCanvasView() {
    setKnowledgeGraphCanvasView({ x: 0, y: 0, scale: 1 });
  }

  function toggleTimelineGroup(label: string) {
    setCollapsedTimelineGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  }

  function collapseAllTimelineGroups(labels: string[]) {
    setCollapsedTimelineGroups(new Set(labels));
  }

  function expandAllTimelineGroups() {
    setCollapsedTimelineGroups(new Set());
  }

  function zoomKnowledgeGraphCanvas(delta: number) {
    setKnowledgeGraphCanvasView((view) => ({
      ...view,
      scale: clampGraphCanvasScale(view.scale + delta),
    }));
  }

  function handleKnowledgeGraphCanvasWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.12 : 0.12;
    zoomKnowledgeGraphCanvas(delta);
  }

  function handleKnowledgeGraphCanvasPanStart(event: MouseEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const target = event.target;
    if (target instanceof Element && target.closest(".workspace-knowledge-map-node, button")) return;
    event.preventDefault();
    graphCanvasPanRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: knowledgeGraphCanvasView.x,
      originY: knowledgeGraphCanvasView.y,
    };
    setKnowledgeGraphCanvasPanning(true);
  }

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
    void openFilePreview(item);
  }

  function handleFileItemKeyDown(event: KeyboardEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activateFileItem(item);
  }

  function canModifyWorkspaceItem(item: WorkspaceFileItemResponse) {
    if (isProtectedWorkspaceDirectory(item, workspaceKind)) return false;
    return item.type === "directory" || item.can_delete;
  }

  function canCopyWorkspaceItem(item: WorkspaceFileItemResponse) {
    return !isProtectedWorkspaceDirectory(item, workspaceKind);
  }

  function canMoveItemTo(item: WorkspaceFileItemResponse, targetDirectory: string) {
    if (isTrashWorkspaceItem(item) || isTrashPath(targetDirectory)) return false;
    if (!canModifyWorkspaceItem(item)) return false;
    if (getParentPath(item.path) === targetDirectory) return false;
    if (item.type === "directory" && isDirectoryInside(item.path, targetDirectory)) return false;
    return true;
  }

  function canPasteInto(targetDirectory: string) {
    if (!clipboardItem) return false;
    if (isTrashPath(targetDirectory)) return false;
    if (clipboardItem.action === "cut") return canMoveItemTo(clipboardItem.item, targetDirectory);
    if (!canCopyWorkspaceItem(clipboardItem.item)) return false;
    if (clipboardItem.item.type === "directory" && isDirectoryInside(clipboardItem.item.path, targetDirectory)) return false;
    return true;
  }

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

  function handleFileDragStart(event: DragEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) {
    if (!canModifyWorkspaceItem(item)) {
      event.preventDefault();
      return;
    }
    setDraggedItem(item);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(WORKSPACE_DRAG_MIME, item.path);
    event.dataTransfer.setData("text/plain", item.path);
  }

  function handleFileDragEnd() {
    setDraggedItem(null);
    setDropTargetPath(null);
  }

  function handleDirectoryDragOver(event: DragEvent<HTMLDivElement | HTMLButtonElement>, targetPath: string) {
    if (isTrashPath(targetPath)) return;
    if (!draggedItem || !hasWorkspaceDrag(event) || !canMoveItemTo(draggedItem, targetPath)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    setDragOver(false);
    setDropTargetPath(targetPath);
  }

  async function handleDirectoryDrop(event: DragEvent<HTMLDivElement | HTMLButtonElement>, targetPath: string) {
    event.preventDefault();
    event.stopPropagation();
    setDragOver(false);
    setDropTargetPath(null);
    if (isTrashPath(targetPath)) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) {
      await handleUpload(files, targetPath);
      return;
    }
    if (!draggedItem || !canMoveItemTo(draggedItem, targetPath)) return;
    await executeMove(draggedItem, targetPath);
    setDraggedItem(null);
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();
    setDragOver(false);
    setDropTargetPath(null);
    if (draggedItem && hasWorkspaceDrag(event)) {
      if (canMoveItemTo(draggedItem, currentPath)) void executeMove(draggedItem, currentPath);
      setDraggedItem(null);
      return;
    }
    void handleUpload(Array.from(event.dataTransfer.files), currentPath);
  }

  const percent = uploadProgress.total > 0 ? Math.round((uploadProgress.current / uploadProgress.total) * 100) : 0;
  const isPersonalWorkspace = workspaceKind === "user";
  const isCustomerWorkspace = workspaceKind === "customer";
  const panelSubtitle = viewMode === "trash" ? "回收站" : isPersonalWorkspace ? "个人文件" : isCustomerWorkspace ? "资料文件" : "项目资料";
  const rootTitle = isPersonalWorkspace ? "个人文件根目录" : isCustomerWorkspace ? "CRM 文件根目录" : "项目资料根目录";
  const canShowKnowledgeIngest = !isPersonalWorkspace && canIngestKnowledge;
  const canShowKnowledgeGraph = workspaceKind === "project" || workspaceKind === "customer";
  const canShowEntityMergeReview = canShowKnowledgeGraph && canIngestKnowledge;
  const knowledgeGraphLabel = isCustomerWorkspace ? "客户情报" : "事件图谱";
  const {
    nodeTitleById,
    graphEntityTypes,
    filteredProfileCards,
    filteredGraphEdges,
    filteredGraphEvents,
    selectedGraphNode,
    selectedGraphNodeEdges,
    selectedGraphNodeEvents,
    selectedGraphEvent,
    selectedGraphNodeSourcePath,
    selectedGraphEventSourcePath,
    timelineHiddenCount,
    timelineGroups,
    timelineGroupLabels,
    graphDegreeById,
    selectedNeighborIds,
    canvasGraphNodes,
    canvasGraphEdges,
    canvasGraphPositions,
    largeGraphNodes,
    largeGraphEdges,
    largeGraphPositions,
    visibleEntityCandidates,
    nativeCounts,
    nativeContextSections,
    crmRecentEvents,
    crmPersonCount,
    crmCompanyCount,
    crmProjectCount,
    crmDatedEventCount,
    crmMostActiveContact,
    crmRelationshipHub,
    crmLatestEvent,
    crmVisibleProfileCards,
    crmCardReason,
    crmSelectedRelations,
    crmSelectedEvents,
    crmCanvasNodes,
    crmCanvasEdges,
    crmCanvasPositions,
  } = buildWorkspaceKnowledgeGraphViewModel({
    knowledgeGraph,
    nativeGraphContext,
    entityMergeCandidates,
    graphSearchTerm,
    graphEntityFilter,
    selectedGraphNodeId,
    selectedGraphEventId,
    graphTimelineFilter,
    graphTimelineDensity,
    isCustomerWorkspace,
  });

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
      <header className="agent-file-panel-header">
        <span className="agent-file-panel-icon"><WorkspaceIcon /></span>
        <div>
          <h2>{workspaceName ?? "当前工作区"}</h2>
          <p>{panelSubtitle}</p>
        </div>
        <div className="agent-file-panel-actions">
          <input className="hidden-file-input" multiple onChange={(event) => void handleUpload(event.target.files)} ref={fileInputRef} type="file" />
          {viewMode === "files" ? (
            <>
              <button aria-label="上传文件" className="workspace-file-primary-action" onClick={() => fileInputRef.current?.click()} title="上传文件" type="button"><PlusIcon /><span>上传</span></button>
              <button aria-label="新建文件夹" className="workspace-file-primary-action" onClick={() => void handleCreateFolder()} title="新建文件夹" type="button"><WorkspaceIcon /><span>新建</span></button>
              <span className="workspace-file-action-menu-wrap" onClick={(event) => event.stopPropagation()}>
                <button aria-expanded={actionMenuOpen} aria-label="更多文件操作" className="workspace-file-action" onClick={() => setActionMenuOpen((value) => !value)} title="更多文件操作" type="button"><MoreIcon /></button>
                {actionMenuOpen ? (
                  <div className="workspace-file-action-menu">
                    <button disabled={loading} onClick={() => { setActionMenuOpen(false); void refresh(); }} type="button"><RefreshIcon />刷新目录</button>
                    <button disabled={!canPasteInto(currentPath)} onClick={() => { setActionMenuOpen(false); void handlePaste(currentPath); }} type="button"><CopyIcon />粘贴到当前文件夹</button>
                    {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                      <button onClick={() => { setActionMenuOpen(false); openMeetingTranscriptForm(); }} type="button"><RefreshIcon />保存转录文本</button>
                    ) : null}
                    {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                      <button onClick={() => { setActionMenuOpen(false); void handleGenerateMinutes(); }} type="button"><NoteIcon />生成纪要与行动项</button>
                    ) : null}
                    {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                      <button onClick={() => { setActionMenuOpen(false); void handleOpenSpeakerMap(); }} type="button"><AgentIcon />说话人映射</button>
                    ) : null}
                    {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                      <button onClick={() => { setActionMenuOpen(false); void handleGenerateMinutes(true); }} type="button"><RefreshIcon />应用修正并重跑纪要</button>
                    ) : null}
                    {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                      <button onClick={() => { setActionMenuOpen(false); setTermCorrectionsOpen(true); }} type="button"><EditIcon />术语纠错</button>
                    ) : null}
                    {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                      <button onClick={() => { setActionMenuOpen(false); void handleMediaTranscribe(); }} type="button"><PlusIcon />上传会议音视频</button>
                    ) : null}
                    {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                      <button onClick={() => { setActionMenuOpen(false); void handleIngestMeeting(); }} type="button"><BrainIcon />录入此会议</button>
                    ) : null}
                    {canShowKnowledgeIngest ? (
                      <button disabled={refreshingKnowledge || pendingIngestCount === 0} onClick={() => { setActionMenuOpen(false); handleRefreshKnowledge(currentPath, true); }} type="button"><RefreshIcon />{refreshingKnowledge ? "正在录入..." : `录入当前文件夹${pendingIngestCount > 0 ? ` (${pendingIngestCount})` : ""}`}</button>
                    ) : null}
                    {canShowKnowledgeGraph ? (
                      <button disabled={knowledgeGraphLoading} onClick={() => { setActionMenuOpen(false); void handleOpenKnowledgeGraph(); }} type="button"><BrainIcon />{knowledgeGraphLoading ? "正在加载..." : knowledgeGraphLabel}</button>
                    ) : null}
                    <button onClick={() => { setActionMenuOpen(false); setViewMode("trash"); navigateTo(""); }} type="button"><TrashIcon />回收站</button>
                  </div>
                ) : null}
              </span>
            </>
          ) : (
            <>
              <button aria-label={isPersonalWorkspace ? "返回个人文件" : "返回项目文件"} className="workspace-file-primary-action" onClick={() => { setViewMode("files"); navigateTo(""); }} title={isPersonalWorkspace ? "个人文件" : "项目文件"} type="button"><WorkspaceIcon /><span>文件</span></button>
              <span className="workspace-file-action-menu-wrap" onClick={(event) => event.stopPropagation()}>
                <button aria-expanded={actionMenuOpen} aria-label="更多回收区操作" className="workspace-file-action" onClick={() => setActionMenuOpen((value) => !value)} title="更多回收区操作" type="button"><MoreIcon /></button>
                {actionMenuOpen ? (
                  <div className="workspace-file-action-menu">
                    <button disabled={loading} onClick={() => { setActionMenuOpen(false); void refresh(); }} type="button"><RefreshIcon />刷新目录</button>
                    <button onClick={() => { setActionMenuOpen(false); void handleClearTrash(); }} type="button"><TrashIcon />清空回收区</button>
                  </div>
                ) : null}
              </span>
            </>
          )}
        </div>
      </header>

      {viewMode === "files" || viewMode === "trash" ? (
        <nav className="workspace-file-breadcrumb" aria-label={isPersonalWorkspace ? "个人文件路径" : "项目文件路径"}>
          {viewMode === "files" ? (
          <div className="workspace-file-nav-controls" aria-label="文件导航" role="group">
            <button aria-label="后退" className="workspace-file-action" disabled={historyIndex <= 0} onClick={goBack} title="后退" type="button"><ChevronLeftIcon /></button>
            <button aria-label="前进" className="workspace-file-action" disabled={historyIndex >= history.length - 1} onClick={goForward} title="前进" type="button"><ChevronRightIcon /></button>
            <button aria-label="上一级" className="workspace-file-action" disabled={!currentPath} onClick={goUp} title="上一级" type="button"><ArrowUpIcon /></button>
          </div>
          ) : (
          <div className="workspace-file-nav-controls" aria-label="文件导航" role="group">
            <button aria-label="返回项目文件" className="workspace-file-action" onClick={() => { setViewMode("files"); navigateTo(""); }} title="返回项目文件" type="button"><ChevronLeftIcon /></button>
          </div>
          )}
          <div className="workspace-file-address-bar">
            {viewMode === "trash" ? (
              <>
                <button
                  aria-label="根目录"
                  className="workspace-file-address-root"
                  onClick={() => { setViewMode("files"); navigateTo(""); }}
                  title={rootTitle}
                  type="button"
                >
                  <WorkspaceIcon />
                </button>
                <span className="workspace-file-path-separator" aria-hidden="true">›</span>
                <button
                  className="workspace-file-path-segment"
                  onClick={() => { setViewMode("files"); navigateTo(""); }}
                  type="button"
                >
                  根目录
                </button>
                <span className="workspace-file-path-separator" aria-hidden="true">›</span>
                <span className="workspace-file-path-segment">回收站</span>
              </>
            ) : (
              <>
                <button
                  aria-label="根目录"
                  className="workspace-file-address-root"
                  data-drop-target={dropTargetPath === "" ? "true" : undefined}
                  onClick={() => navigateTo("")}
                  onDragOver={(event) => handleDirectoryDragOver(event, "")}
                  onDrop={(event) => void handleDirectoryDrop(event, "")}
                  title={rootTitle}
                  type="button"
                >
                  <WorkspaceIcon />
                </button>
                <span className="workspace-file-path-separator" aria-hidden="true">›</span>
                <button
                  className="workspace-file-path-segment"
                  data-drop-target={dropTargetPath === "" ? "true" : undefined}
                  onClick={() => navigateTo("")}
                  onDragOver={(event) => handleDirectoryDragOver(event, "")}
                  onDrop={(event) => void handleDirectoryDrop(event, "")}
                  type="button"
                >
                  根目录
                </button>
                {breadcrumb.map((part) => (
                  <span className="workspace-file-path-part" key={part.path}>
                    <span className="workspace-file-path-separator" aria-hidden="true">›</span>
                    <button
                      className="workspace-file-path-segment"
                      data-drop-target={dropTargetPath === part.path ? "true" : undefined}
                      onClick={() => navigateTo(part.path)}
                      onDragOver={(event) => handleDirectoryDragOver(event, part.path)}
                      onDrop={(event) => void handleDirectoryDrop(event, part.path)}
                      type="button"
                    >
                      {part.name}
                    </button>
                  </span>
                ))}
              </>
            )}
          </div>
        </nav>
      ) : null}

      {showMeetingWorkflowToolbar ? (
        <div className="workspace-meeting-toolbar" data-testid="meeting-toolbar">
          <span className="workspace-meeting-toolbar-label">会议工作流</span>
          <div className="workspace-meeting-toolbar-actions">
            <button
              className="workspace-file-primary-action"
              disabled={refreshingKnowledge}
              onClick={() => handleMediaTranscribe()}
              title="上传会议音文件到当前文件夹并自动转录"
              type="button"
            >
              <PlusIcon /><span>上传/转写录音</span>
            </button>
            <button
              className="workspace-file-primary-action"
              disabled={refreshingKnowledge}
              onClick={() => openMeetingTranscriptForm()}
              title="将已有的会议转录文本保存到当前文件夹"
              type="button"
            >
              <NoteIcon /><span>保存转录文本</span>
            </button>
            <button
              className="workspace-file-primary-action"
              disabled={!isLegitimateMeetingFolder || refreshingKnowledge}
              onClick={() => void handleOpenSpeakerMap()}
              title={!isLegitimateMeetingFolder ? "请在具体会议文件夹中使用此功能。" : "为当前会议的检测说话人设置显示名称"}
              type="button"
            >
              <AgentIcon /><span>说话人映射</span>
            </button>
            <button
              className="workspace-file-primary-action"
              disabled={!isLegitimateMeetingFolder || refreshingKnowledge}
              onClick={() => setTermCorrectionsOpen(true)}
              title={!isLegitimateMeetingFolder ? "请在具体会议文件夹中使用此功能。" : "添加需要纠正的术语"}
              type="button"
            >
              <EditIcon /><span>术语纠错</span>
            </button>
            <button
              className="workspace-file-primary-action"
              disabled={!isLegitimateMeetingFolder || refreshingKnowledge}
              onClick={() => void handleGenerateMinutes()}
              title={!isLegitimateMeetingFolder ? "请在具体会议文件夹中使用此功能。" : "从当前会议的转录文本生成纪要与行动项"}
              type="button"
            >
              <NoteIcon /><span>生成纪要与行动项</span>
            </button>
            <button
              className="workspace-file-primary-action"
              disabled={!isLegitimateMeetingFolder || refreshingKnowledge}
              onClick={() => void handleGenerateMinutes(true)}
              title="如果会议转录已更新，重新生成纪要与行动项（创建新版本）"
              type="button"
            >
              <RefreshIcon /><span>重跑纪要</span>
            </button>
            <button
              className="workspace-file-primary-action"
              disabled={!isLegitimateMeetingFolder || refreshingKnowledge}
              onClick={() => void handleIngestMeeting()}
              title={!isLegitimateMeetingFolder ? "请在具体会议文件夹中使用此功能。" : "将当前会议组合成 GBrain-ready 页面"}
              type="button"
            >
              <BrainIcon /><span>录入此会议</span>
            </button>
            {/* Actions-only ingest entry - only show in meeting root */}
            {isLegitimateMeetingFolder ? (
              <button
                className="workspace-file-primary-action"
                disabled={refreshingKnowledge}
                onClick={() => void handleIngestMeeting(true)}
                title="仅录入行动项，不包含纪要和转录上下文"
                type="button"
              >
                <BrainIcon /><span>录入行动项</span>
              </button>
            ) : null}
            {isLegitimateMeetingFolder ? (
              <>
                <button
                  className="workspace-file-primary-action"
                  disabled={refreshingKnowledge}
                  onClick={() => void handleRetryMeeting("transcribe")}
                  title="重试之前失败的音视频转录操作"
                  type="button"
                >
                  <RefreshIcon /><span>重试转录</span>
                </button>
                <button
                  className="workspace-file-primary-action"
                  disabled={refreshingKnowledge}
                  onClick={() => void handleRetryMeeting("generate_minutes")}
                  title="重试之前失败的纪要生成操作"
                  type="button"
                >
                  <RefreshIcon /><span>重试纪要生成</span>
                </button>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
      {showMeetingWorkflowToolbar && isMeetingRoot && currentPath === MEETING_ROOT_PATH && !hasMeetingWorkflowDirs ? (
        <p className="agent-file-panel-note" style={{ margin: "8px 12px" }}>
          会议资料请放入 20-会议与沟通；可先上传会议音视频或保存已有转录文本。
        </p>
      ) : null}

      {uploadProgress.active ? (
        <div className="workspace-upload-progress">
          <div className="workspace-upload-progress-meta">
            <span>正在上传 {uploadProgress.filename}</span>
            <strong>{percent}%</strong>
          </div>
          <div className="workspace-upload-progress-track"><span style={{ width: `${percent}%` }} /></div>
        </div>
      ) : null}

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
          <div className="workspace-trash-table">
            {visibleItems.map((item) => (
              <div className="workspace-trash-row" key={`${item.id}-${item.path}`}>
                <span className="workspace-trash-name">{item.name}</span>
                <span className="workspace-trash-path">{item.path}</span>
                <span>{formatSize(item.size)}</span>
                <span>{item.deleted_at ? parseApiDate(item.deleted_at).toLocaleString("zh-CN") : ""}</span>
                <div>
                  <button disabled={!item.can_restore} onClick={() => void handleRestore(item)} type="button">还原</button>
                  <button disabled={!item.can_delete} onClick={() => void handlePermanentDelete(item)} type="button">删除</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="workspace-file-list" role="list">
            {visibleItems.map((item) => {
              const isDirectory = item.type === "directory";
              const isTrashDirectory = isTrashWorkspaceItem(item);
              const fileKind = isDirectory ? "directory" : getFileKind(item.name);
              const ragStatus = getRagStatusMeta(item.rag_status);
              const canDragItem = canModifyWorkspaceItem(item);
              const isDropTarget = isDirectory && dropTargetPath === item.path;
              return (
                <div
                  className={`workspace-file-row is-${fileKind}`}
                  data-cut={clipboardItem?.action === "cut" && clipboardItem.item.path === item.path ? "true" : undefined}
                  data-drop-target={isDropTarget ? "true" : undefined}
                  data-selected={filePreview?.item.path === item.path ? "true" : undefined}
                  draggable={canDragItem}
                  key={item.path}
                  onClick={() => activateFileItem(item)}
                  onContextMenu={(event) => openFileContextMenu(event, item)}
                  onDragEnd={handleFileDragEnd}
                  onDragOver={isDirectory ? (event) => handleDirectoryDragOver(event, item.path) : undefined}
                  onDragStart={(event) => handleFileDragStart(event, item)}
                  onDrop={isDirectory ? (event) => void handleDirectoryDrop(event, item.path) : undefined}
                  onKeyDown={(event) => handleFileItemKeyDown(event, item)}
                  role="listitem"
                  tabIndex={0}
                  title={item.path}
                >
                  <span className="workspace-file-row-icon">{isTrashDirectory ? <TrashIcon /> : isDirectory ? <WorkspaceIcon /> : <NoteIcon />}</span>
                  <span className="workspace-file-row-name">{item.name}</span>
                  <span className="workspace-file-row-size">{isTrashDirectory ? "回收站" : isDirectory ? "文件夹" : formatSize(item.size)}</span>
                  {isTrashDirectory ? (
                    <span className="workspace-rag-badge is-muted">回收站</span>
                  ) : isDirectory ? (
                    <span className="workspace-rag-badge is-directory">目录</span>
                  ) : isPersonalWorkspace ? (
                    <span className="workspace-rag-badge is-muted" title="个人工作台文件不会自动进入知识库">暂存</span>
                  ) : (
                    <span className={`workspace-rag-badge is-${ragStatus.tone}`} title={ragStatus.title}>
                      {ragStatus.label}
                      {item.rag_status === "failed" && canShowKnowledgeIngest ? (
                        <button
                          className="workspace-rag-retry"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleRefreshKnowledge(item.path, false, item);
                          }}
                          title="重新处理此文件"
                          type="button"
                        >重试</button>
                      ) : null}
                      {item.rag_status === "partial" || item.rag_status === "pending_transcription" ? (
                        <button
                          className="workspace-rag-retry"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (item.path.startsWith("20-会议与沟通")) {
                              // Navigate to meeting folder and show retry
                              setCurrentPath(item.path.split("/").slice(0, -1).join("/"));
                            }
                          }}
                          title="查看详情"
                          type="button"
                        >详情</button>
                      ) : null}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )
      ) : null}
      {contextMenu ? (
        <div
          className="workspace-file-context-menu"
          onClick={(event) => event.stopPropagation()}
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {contextMenu.kind === "blank" ? (
            <>
              <button disabled={loading} onClick={() => runContextAction(() => void refresh())} type="button"><RefreshIcon />刷新</button>
              <button disabled={!canPasteInto(contextMenu.targetDirectory)} onClick={() => runContextAction(() => void handlePaste(contextMenu.targetDirectory))} type="button"><CopyIcon />粘贴到此处</button>
              <button disabled={isTrashPath(contextMenu.targetDirectory)} onClick={() => runContextAction(() => handleCreateFolder(contextMenu.targetDirectory))} type="button"><WorkspaceIcon />新建文件夹</button>
            </>
          ) : contextMenu.item?.type === "directory" ? (
            <>
              <button onClick={() => runContextAction(() => activateFileItem(contextMenu.item!))} type="button">{isTrashWorkspaceItem(contextMenu.item) ? <TrashIcon /> : <WorkspaceIcon />}{isTrashWorkspaceItem(contextMenu.item) ? "打开回收站" : "打开"}</button>
              <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCut(contextMenu.item!))} type="button"><MoveIcon />剪切</button>
              <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canCopyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCopy(contextMenu.item!))} type="button"><CopyIcon />复制</button>
              <button disabled={!canPasteInto(contextMenu.item.path)} onClick={() => runContextAction(() => void handlePaste(contextMenu.item!.path))} type="button"><CopyIcon />粘贴到此处</button>
              {canShowKnowledgeIngest ? (
                <button
                  disabled={refreshingKnowledge || countPendingIngestFiles([contextMenu.item]) === 0 || isTrashWorkspaceItem(contextMenu.item)}
                  onClick={() => runContextAction(() => handleRefreshKnowledge(contextMenu.item!.path, true, contextMenu.item))}
                  type="button"
                >
                  <RefreshIcon />录入此文件夹
                </button>
              ) : null}
              <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleRename(contextMenu.item!))} type="button"><EditIcon />重命名</button>
              <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => void handleDelete(contextMenu.item!))} type="button"><TrashIcon />删除</button>
            </>
          ) : contextMenu.item ? (
            <>
              <button onClick={() => runContextAction(() => activateFileItem(contextMenu.item!))} type="button"><NoteIcon />预览</button>
              <button onClick={() => runContextAction(() => void downloadWorkspaceFile(contextMenu.item!))} type="button"><ArchiveIcon />下载</button>
              <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCut(contextMenu.item!))} type="button"><MoveIcon />剪切</button>
              <button disabled={!canCopyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCopy(contextMenu.item!))} type="button"><CopyIcon />复制</button>
              {canShowKnowledgeIngest ? (
                <button
                  disabled={refreshingKnowledge || countPendingIngestFiles([contextMenu.item]) === 0 || isTrashWorkspaceItem(contextMenu.item)}
                  onClick={() => runContextAction(() => handleRefreshKnowledge(contextMenu.item!.path, false, contextMenu.item))}
                  type="button"
                >
                  <RefreshIcon />录入此文件
                </button>
              ) : null}
              {/* Actions-only ingest for actions-latest.md */}
              {canShowKnowledgeIngest && contextMenu.item && !isTrashWorkspaceItem(contextMenu.item)
                && contextMenu.item.name === "actions-latest.md"
                && inferMeetingFolder(contextMenu.item.path) !== null ? (
                <button
                  disabled={refreshingKnowledge}
                  onClick={() => runContextAction(async () => {
                    if (!workspaceId) return;
                    setCurrentPath(inferMeetingFolder(contextMenu.item!.path)!);
                    setPendingConfirmation({
                      title: "录入行动项（仅行动项）",
                      detail: [
                        `当前工作区：${workspaceName ?? workspaceKind}`,
                        `路径：${inferMeetingFolder(contextMenu.item!.path)!}/05-行动项/actions-latest.md`,
                        "范围：仅录入行动项文件，不包含会议纪要和转录文本。",
                        "将标记为「仅行动项」，低上下文完整度。",
                        "如需要完整会议知识，建议改为录入完整会议。",
                      ].join("\\n"),
                      confirmLabel: "录入行动项",
                      tone: "warning",
                      onConfirm: async () => {
                        await handleIngestMeeting(true);
                      },
                    });
                  })}
                  type="button"
                >
                  <BrainIcon />录入行动项（仅行动项）
                </button>
              ) : null}
              {/* Retry failed ingest */}
              {contextMenu.item && !isTrashWorkspaceItem(contextMenu.item)
                && contextMenu.item.rag_status === "failed" ? (
                <button
                  disabled={refreshingKnowledge}
                  onClick={() => runContextAction(() => {
                    handleRefreshKnowledge(
                      contextMenu.item!.path,
                      false,
                      contextMenu.item,
                    );
                  })}
                  type="button"
                >
                  <RefreshIcon />重新处理此文件
                </button>
              ) : null}
              {/* Retry failed meeting transcription - for transcript files */}
              {contextMenu.item && !isTrashWorkspaceItem(contextMenu.item)
                && contextMenu.item.name?.startsWith("transcript-")
                && (contextMenu.item.rag_status === "failed" || contextMenu.item.rag_status === "partial")
                && inferMeetingFolder(contextMenu.item.path) !== null ? (
                <button
                  disabled={refreshingKnowledge}
                  onClick={() => runContextAction(async () => {
                    if (!workspaceId) return;
                    // Navigate to meeting folder and trigger regenerate
                    setCurrentPath(inferMeetingFolder(contextMenu.item!.path)!);
                    setPendingConfirmation({
                      title: "重新生成纪要与行动项",
                      detail: `基于现有转录重新生成纪要与行动项。转录状态为 ${contextMenu.item!.rag_status}，部分失败内容可能无法覆盖。`,
                      confirmLabel: "重新生成",
                      tone: "warning",
                      onConfirm: async () => {
                        await handleGenerateMinutes(true);
                      },
                    });
                  })}
                  type="button"
                >
                  <NoteIcon />重新生成纪要
                </button>
              ) : null}
              {/* Meeting file context actions — only when a valid meeting folder can be inferred */}
              {contextMenu.item && !isTrashWorkspaceItem(contextMenu.item) && inferMeetingFolder(contextMenu.item.path) !== null && (
                <>
                  {isMeetingAudioFile(contextMenu.item.name) ? (
                    <button
                      disabled={refreshingKnowledge}
                      onClick={() => runContextAction(async () => {
                        if (!workspaceId) return;
                        const item = contextMenu.item!;
                        const meetingFolder = inferMeetingFolder(item.path)!;
                        setNotice("正在读取文件并转录...");
                        setRefreshingKnowledge(true);
                        try {
                          const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
                          const file = new File([blob], item.name, { type: blob.type });
                          const resp = await transcribeMeetingMedia(apiOptions, workspaceId, meetingFolder, file);
                          if (resp.agent_run) setLatestAgentRun(resp.agent_run);
                          const parts: string[] = [];
                          if (resp.transcription_status === "failed") parts.push("转录失败");
                          else if (resp.transcription_status === "partial") parts.push(`部分转录完成（${resp.segment_count}段）`);
                          else parts.push(`转录完成（${resp.segment_count}段）`);
                          if (resp.warnings.length > 0) parts.push(`${resp.warnings.length} 条警告`);
                          if (resp.token_cost > 0) parts.push(`token：${resp.token_cost}`);
                          setNotice(parts.join("，"));
                          await refresh();
                        } catch (txErr: unknown) {
                          setError(txErr instanceof Error ? txErr.message : "转录失败");
                        } finally {
                          setRefreshingKnowledge(false);
                        }
                      })}
                      type="button"
                    >
                      <NoteIcon />转录此音视频
                    </button>
                  ) : null}
                  {isMeetingTranscriptSourceFile(contextMenu.item) ? (
                    <button
                      disabled={refreshingKnowledge}
                      onClick={() => runContextAction(async () => {
                        if (!workspaceId) return;
                        const item = contextMenu.item!;
                        const meetingFolder = inferMeetingFolder(item.path)!;
                        setNotice("正在保存转录文本并生成纪要...");
                        setRefreshingKnowledge(true);
                        try {
                          const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
                          const lower = item.name.toLowerCase();
                          if (lower.endsWith(".docx")) {
                            const file = new File([blob], item.name, { type: blob.type });
                            await saveMeetingTranscriptFromFile(apiOptions, workspaceId, meetingFolder, file);
                          } else {
                            const text = await blob.text();
                            await saveMeetingTranscript(apiOptions, workspaceId, {
                              folder_path: meetingFolder,
                              content: text,
                              input_type: lower.endsWith(".md") ? "md" : "txt",
                              original_filename: item.name,
                            });
                          }
                          const genResp = await generateMeetingMinutesAndActions(apiOptions, workspaceId, { folder_path: meetingFolder });
                          if (genResp.agent_run) setLatestAgentRun(genResp.agent_run);
                          setNotice(`纪要已生成（模型：${genResp.model_used}）`);
                          await refresh();
                        } catch (genErr: unknown) {
                          if (genErr instanceof Error && genErr.message.includes("已存在纪要与行动项")) {
                            setPendingConfirmation({
                              title: "已存在纪要与行动项",
                              detail: "当前会议已有纪要与行动项。重新生成将创建新版本（v2/v3…）并更新 latest。是否继续？",
                              confirmLabel: "重新生成",
                              tone: "warning",
                              onConfirm: async () => {
                                if (!workspaceId || !meetingFolder) return;
                                setRefreshingKnowledge(true);
                                try {
                                  const reBlob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
                                  const reLower = item.name.toLowerCase();
                                  if (reLower.endsWith(".docx")) {
                                    await saveMeetingTranscriptFromFile(apiOptions, workspaceId, meetingFolder, new File([reBlob], item.name, { type: reBlob.type }));
                                  } else {
                                    const reText = await reBlob.text();
                                    await saveMeetingTranscript(apiOptions, workspaceId, { folder_path: meetingFolder, content: reText, input_type: reLower.endsWith(".md") ? "md" : "txt", original_filename: item.name });
                                  }
                                  const reGenResp = await generateMeetingMinutesAndActions(apiOptions, workspaceId, { folder_path: meetingFolder, regenerate: true });
                                  if (reGenResp.agent_run) setLatestAgentRun(reGenResp.agent_run);
                                  setNotice(`纪要已重新生成（模型：${reGenResp.model_used}）`);
                                  await refresh();
                                } catch (reErr: unknown) {
                                  setError(reErr instanceof Error ? reErr.message : "重新生成失败");
                                } finally {
                                  setRefreshingKnowledge(false);
                                }
                              },
                            });
                            return;
                          }
                          setError(genErr instanceof Error ? genErr.message : "生成纪要失败");
                        } finally {
                          setRefreshingKnowledge(false);
                        }
                      })}
                      type="button"
                    >
                      <NoteIcon />用此转录生成纪要
                    </button>
                  ) : null}
                  {contextMenu.item?.name === "actions-latest.md" && inferMeetingFolder(contextMenu.item.path) !== null ? (
                    <button
                      disabled={refreshingKnowledge}
                      onClick={() => runContextAction(async () => {
                        if (!workspaceId) return;
                        const item = contextMenu.item!;
                        const meetingFolder = inferMeetingFolder(item.path)!;
                        setRefreshingKnowledge(true);
                        setError(null);
                        try {
                          const resp = await ingestMeetingToGBrain(apiOptions, workspaceId!, {
                            folder_path: meetingFolder,
                            single_file_path: item.path,
                          });
                          const msgs = [`已录入 ${resp.ingested_files.length} 个文件`];
                          if (resp.warning) msgs.push(`注意：${resp.warning}`);
                          setNotice(msgs.join("，"));
                          if (resp.agent_run) setLatestAgentRun(resp.agent_run);
                          await refresh();
                        } catch (ingestErr: unknown) {
                          setError(ingestErr instanceof Error ? ingestErr.message : "录入失败");
                        } finally {
                          setRefreshingKnowledge(false);
                        }
                      })}
                      type="button"
                    >
                      <BrainIcon />录入此行动项
                    </button>
                  ) : null}
                </>
              )}
              <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleRename(contextMenu.item!))} type="button"><EditIcon />重命名</button>
              <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => void handleDelete(contextMenu.item!))} type="button"><TrashIcon />删除</button>
              <button onClick={() => runContextAction(() => void onReferenceFile?.(contextMenu.item!))} type="button"><NoteIcon />引用文件</button>
              <button onClick={() => runContextAction(() => void openFilePreview(contextMenu.item!))} type="button"><NoteIcon />详细信息</button>
            </>
          ) : null}
        </div>
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
        <div className="workspace-text-prompt-overlay" onClick={() => !termCorrectionsBusy && setTermCorrectionsOpen(false)}>
          <div
            className="workspace-text-prompt"
            onClick={(event) => event.stopPropagation()}
            style={{ maxWidth: 500 }}
          >
            <header>
              <strong>术语纠错</strong>
              <button disabled={termCorrectionsBusy} onClick={() => setTermCorrectionsOpen(false)} type="button">×</button>
            </header>
            <div style={{ background: "var(--warning)/0.1", padding: "8px 12px", borderRadius: 6, marginBottom: 10, fontSize: "0.9em", lineHeight: 1.5 }}>
              <strong>转录中这些词是否需要修正？</strong>
              <p style={{ margin: "4px 0 0", opacity: 0.75 }}>
                音视频转录可能将专业术语、人名、地名词识别错误。请检查并修正：添加原识别词和正确写法，例如 "波离" → "玻璃"、"五矿" → "5mm"。
                已保存的术语会在下次生成纪要时自动应用。跳过将保留原始识别结果，未确认术语在纪要中标记为「待确认」。
              </p>
            </div>
            {termCorrections.length > 0 ? (
              <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>原识别</th>
                    <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>建议修正</th>
                    <th style={{ width: 60, borderBottom: "1px solid #ccc" }} />
                  </tr>
                </thead>
                <tbody>
                  {termCorrections.map((tc, idx) => (
                    <tr key={idx}>
                      <td style={{ padding: "4px 8px" }}>{tc.original}</td>
                      <td style={{ padding: "4px 8px" }}>{tc.corrected}</td>
                      <td style={{ padding: "4px 8px" }}>
                        <button
                          disabled={termCorrectionsBusy}
                          onClick={() => setTermCorrections((prev) => prev.filter((_, i) => i !== idx))}
                          type="button"
                          style={{ background: "none", border: "none", color: "#d00", cursor: "pointer" }}
                        >×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <input
                disabled={termCorrectionsBusy}
                onChange={(e) => setTermEditOriginal(e.target.value)}
                placeholder="原识别"
                style={{ flex: 1 }}
                value={termEditOriginal}
              />
              <input
                disabled={termCorrectionsBusy}
                onChange={(e) => setTermEditCorrected(e.target.value)}
                placeholder="建议修正"
                style={{ flex: 1 }}
                value={termEditCorrected}
              />
              <button
                disabled={termCorrectionsBusy || !termEditOriginal.trim() || !termEditCorrected.trim()}
                onClick={() => {
                  setTermCorrections((prev) => [...prev, { original: termEditOriginal.trim(), corrected: termEditCorrected.trim() }]);
                  setTermEditOriginal("");
                  setTermEditCorrected("");
                }}
                type="button"
              >添加</button>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button disabled={termCorrectionsBusy} onClick={() => setTermCorrectionsOpen(false)} type="button">跳过</button>
              <button disabled={termCorrectionsBusy || termCorrections.length === 0} onClick={() => void handleSaveTermCorrections()} type="button">保存</button>
            </div>
          </div>
        </div>
      ) : null}
      {speakerMapOpen ? (
        <div className="workspace-text-prompt-overlay" onClick={() => !speakerMapLoading && setSpeakerMapOpen(false)}>
          <div
            className="workspace-text-prompt"
            onClick={(event) => event.stopPropagation()}
            style={{ maxWidth: 500 }}
          >
            <header>
              <strong>说话人映射</strong>
              <button disabled={speakerMapLoading} onClick={() => setSpeakerMapOpen(false)} type="button">×</button>
            </header>
            <div style={{ background: "var(--warning)/0.1", padding: "8px 12px", borderRadius: 6, marginBottom: 10, fontSize: "0.9em", lineHeight: 1.5 }}>
              <strong>需要标记发言人吗？</strong>
              <p style={{ margin: "4px 0 0", opacity: 0.75 }}>
                系统已自动检测到以下说话人。为每个人填写真实姓名，生成纪要时就会使用姓名而非 "Speaker 1"。
                跳过将保留为「待确认」，可以在后续随时补充。
              </p>
            </div>
            {speakerMapLoading ? (
              <p>正在读取说话人信息...</p>
            ) : detectedSpeakers.length === 0 ? (
              <p>未检测到说话人。可以跳过此步骤，未确认项将被标记为「待确认」。</p>
            ) : (
              <div>
                <p style={{ opacity: 0.7, marginBottom: 8, fontSize: "0.85em" }}>点击说话人ID下方的输入框，填写显示名称。</p>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>说话人ID</th>
                      <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>显示名称</th>
                      <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>发言占比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detectedSpeakers.map((sp) => (
                      <tr key={sp.speaker_id}>
                        <td style={{ padding: "4px 8px" }}>{sp.speaker_id}</td>
                        <td style={{ padding: "4px 8px" }}>
                          <input
                            style={{ width: "100%", boxSizing: "border-box" }}
                            value={speakerMapNames[sp.speaker_id] ?? sp.display_name}
                            onChange={(e) => setSpeakerMapNames((prev) => ({ ...prev, [sp.speaker_id]: e.target.value }))}
                          />
                        </td>
                        <td style={{ padding: "4px 8px" }}>{sp.ratio}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div style={{ marginTop: 12, display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button disabled={speakerMapLoading} onClick={() => setSpeakerMapOpen(false)} type="button">跳过</button>
              <button disabled={speakerMapLoading || detectedSpeakers.length === 0} onClick={() => void handleSaveSpeakerMap()} type="button">保存映射</button>
            </div>
          </div>
        </div>
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
    {knowledgeGraphOpen && isCustomerWorkspace ? (
      <div className="crm-intelligence-overlay" role="dialog" aria-modal="true" aria-label="CRM 客户情报">
        <section className="crm-intelligence-shell">
          <header className="crm-intelligence-header">
            <div>
              <span>CRM 客户情报</span>
              <strong>{workspaceName || "客户工作区"}</strong>
              <small>客户情报、关系网和近期互动来自受限客户情报数据。</small>
            </div>
            <div className="crm-intelligence-header-actions">
              <button disabled={knowledgeGraphLoading} onClick={() => void handleOpenKnowledgeGraph()} type="button"><RefreshIcon />刷新</button>
              <button disabled={crmCanvasNodes.length === 0} onClick={() => { resetKnowledgeGraphCanvasView(); setKnowledgeGraphCanvasOpen(true); }} type="button"><MaximizeIcon />大画布</button>
              <button aria-label="关闭 CRM 客户情报" onClick={closeKnowledgeGraph} type="button"><XmarkIcon /></button>
            </div>
          </header>
          <div className="crm-intelligence-toolbar">
            <label>
              <SearchIcon />
              <input
                onChange={(event) => setGraphSearchTerm(event.target.value)}
                placeholder="搜索客户、联系人、项目或事件"
                type="search"
                value={graphSearchTerm}
              />
            </label>
            <div>
              {[
                { value: "all", label: "全部" },
                { value: "customer_person_source_record", label: "联系人" },
                { value: "customer_company_source_record", label: "公司" },
                { value: "customer_project_source_record", label: "项目" },
              ].map((item) => (
                <button
                  aria-pressed={graphEntityFilter === item.value}
                  className={graphEntityFilter === item.value ? "is-active" : ""}
                  key={item.value}
                  onClick={() => setGraphEntityFilter(item.value)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          {knowledgeGraphLoading ? <p className="crm-intelligence-message">正在读取客户情报...</p> : null}
          {knowledgeGraphError ? <p className="crm-intelligence-message is-error">{knowledgeGraphError}</p> : null}
          {!knowledgeGraphLoading && knowledgeGraph ? (
            <div className="crm-intelligence-body">
              <aside className="crm-intelligence-roster">
                <section className="crm-intelligence-brief" aria-label="客户情报摘要">
                  <div className="crm-intelligence-list-head">
                    <strong>这批资料能快速看到</strong>
                    <small>按互动和关系自动提取</small>
                  </div>
                  <div className="crm-intelligence-brief-list">
                    {crmMostActiveContact ? (
                      <button onClick={() => setSelectedGraphNodeId(crmMostActiveContact.id)} type="button">
                        <span>最活跃联系人</span>
                        <strong title={crmMostActiveContact.title}>{crmMostActiveContact.title}</strong>
                        <small>{crmMostActiveContact.event_count} 次互动 · {crmMostActiveContact.relation_count} 条关系</small>
                      </button>
                    ) : null}
                    {crmRelationshipHub ? (
                      <button onClick={() => setSelectedGraphNodeId(crmRelationshipHub.id)} type="button">
                        <span>关系中心</span>
                        <strong title={crmRelationshipHub.title}>{crmRelationshipHub.title}</strong>
                        <small>{crmEntityLabel(crmRelationshipHub.entity_type)} · 连接 {crmRelationshipHub.relation_count} 条关系</small>
                      </button>
                    ) : null}
                    {crmLatestEvent ? (
                      <button
                        onClick={() => {
                          setSelectedGraphNodeId(crmLatestEvent.entity_id);
                          setSelectedGraphEventId(crmLatestEvent.id);
                        }}
                        type="button"
                      >
                        <span>最近互动</span>
                        <strong title={crmLatestEvent.title}>{crmShortSource(crmLatestEvent.title)}</strong>
                        <small>{crmLatestEvent.date || "未标日期"} · {nodeTitleById.get(crmLatestEvent.entity_id) || "客户对象"}</small>
                      </button>
                    ) : null}
                    {!crmMostActiveContact && !crmRelationshipHub && !crmLatestEvent ? (
                      <p>当前筛选下还没有足够的关系或互动记录。</p>
                    ) : null}
                  </div>
                </section>
                <div className="crm-intelligence-scope" aria-label="资料范围">
                  <span><strong>{crmPersonCount}</strong><small>联系人</small></span>
                  <span><strong>{crmCompanyCount}</strong><small>公司</small></span>
                  <span><strong>{crmProjectCount}</strong><small>项目</small></span>
                  <span><strong>{crmDatedEventCount}/{filteredGraphEvents.length}</strong><small>有日期互动</small></span>
                </div>
                <div className="crm-intelligence-list-head">
                  <strong>可追踪对象</strong>
                  <small>{crmVisibleProfileCards.length} / {filteredProfileCards.length}</small>
                </div>
                <div className="crm-intelligence-roster-list">
                  {crmVisibleProfileCards.map((card) => (
                    <button
                      className={selectedGraphNodeId === card.id ? "is-selected" : ""}
                      key={card.id}
                      onClick={() => setSelectedGraphNodeId(card.id)}
                      type="button"
                    >
                      <span>{crmEntityLabel(card.entity_type)}</span>
                      <strong title={card.title}>{card.title}</strong>
                      <small>{crmCardReason(card)}</small>
                    </button>
                  ))}
                  {crmVisibleProfileCards.length === 0 ? <p>没有匹配的客户对象。</p> : null}
                </div>
              </aside>
              <main className="crm-intelligence-main">
                <section className="crm-intelligence-map-card">
                  <div className="crm-intelligence-section-title">
                    <div>
                      <strong>关系网</strong>
                      <small>点击节点查看业务关系，默认只显示当前筛选下的关键对象。</small>
                    </div>
                    <span>{crmCanvasNodes.length} 节点 · {crmCanvasEdges.length} 关系</span>
                  </div>
                  <div className="crm-intelligence-map">
                    {crmCanvasNodes.length > 0 ? (
                      <svg viewBox="0 0 720 420" preserveAspectRatio="xMidYMid meet">
                        <defs>
                          <marker id="crm-intelligence-arrow" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
                            <path d="M0,0 L7,3 L0,6 Z" />
                          </marker>
                        </defs>
                        {crmCanvasEdges.map((edge) => {
                          const from = crmCanvasPositions.get(edge.from);
                          const to = crmCanvasPositions.get(edge.to);
                          if (!from || !to) return null;
                          const isActive = Boolean(selectedGraphNode && (edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id));
                          return (
                            <g className={isActive ? "is-active" : ""} key={edge.id}>
                              <line markerEnd="url(#crm-intelligence-arrow)" x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
                              <title>{`${nodeTitleById.get(edge.from) || edge.from} · ${crmRelationLabel(edge.relation_type)} · ${nodeTitleById.get(edge.to) || edge.to}`}</title>
                            </g>
                          );
                        })}
                        {crmCanvasNodes.map((node) => {
                          const point = crmCanvasPositions.get(node.id);
                          if (!point) return null;
                          const isSelected = selectedGraphNodeId === node.id;
                          const isNeighbor = selectedNeighborIds.has(node.id);
                          return (
                            <g
                              className={`${isSelected ? "is-selected" : ""} ${isNeighbor ? "is-neighbor" : ""}`}
                              key={node.id}
                              onClick={() => setSelectedGraphNodeId(node.id)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") {
                                  event.preventDefault();
                                  setSelectedGraphNodeId(node.id);
                                }
                              }}
                              role="button"
                              tabIndex={0}
                              transform={`translate(${point.x} ${point.y})`}
                            >
                              <circle fill={graphEntityTypeColor(node.entity_type)} r={isSelected ? 25 : 20} />
                              <text textAnchor="middle" y="4">{graphCanvasLabel(node.title)}</text>
                              <title>{`${node.title} · ${crmEntityLabel(node.entity_type)}`}</title>
                            </g>
                          );
                        })}
                      </svg>
                    ) : (
                      <p>没有可展示的关系网。</p>
                    )}
                  </div>
                </section>
                <section className="crm-intelligence-timeline-card">
                  <div className="crm-intelligence-section-title">
                    <div>
                      <strong>近期互动</strong>
                      <small>事件可点击，右侧会显示对应详情和来源。</small>
                    </div>
                    <div className="crm-intelligence-timeline-tabs">
                      {[
                        { key: "all", label: "全部" },
                        { key: "dated", label: "有日期" },
                        { key: "selected", label: "当前对象" },
                      ].map((item) => (
                        <button
                          aria-pressed={graphTimelineFilter === item.key}
                          className={graphTimelineFilter === item.key ? "is-active" : ""}
                          disabled={item.key === "selected" && !selectedGraphNode}
                          key={item.key}
                          onClick={() => setGraphTimelineFilter(item.key as typeof graphTimelineFilter)}
                          type="button"
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="crm-intelligence-timeline">
                    {crmRecentEvents.map((event) => (
                      <button
                        className={selectedGraphEventId === event.id ? "is-selected" : ""}
                        key={event.id}
                        onClick={() => {
                          setSelectedGraphNodeId(event.entity_id);
                          setSelectedGraphEventId(event.id);
                        }}
                        type="button"
                      >
                        <span>{event.date || "未标日期"}</span>
                        <strong title={event.title}>{crmShortSource(event.title)}</strong>
                        <small>{nodeTitleById.get(event.entity_id) || "客户对象"} · {crmShortSource(event.source_file)}</small>
                      </button>
                    ))}
                    {crmRecentEvents.length === 0 ? <p>没有匹配的互动记录。</p> : null}
                  </div>
                </section>
              </main>
              <aside className="crm-intelligence-detail">
                {selectedGraphNode ? (
                  <>
                    <div className="crm-intelligence-detail-head">
                      <span>{crmEntityLabel(selectedGraphNode.entity_type)}</span>
                      <strong title={selectedGraphNode.title}>{selectedGraphNode.title}</strong>
                      <small>{crmShortSource(selectedGraphNode.source_file || selectedGraphNode.file)}</small>
                    </div>
                    <div className="crm-intelligence-actions">
                      <button disabled={!selectedGraphNodeSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphNodeSourcePath)} type="button">查看来源</button>
                      {canShowEntityMergeReview ? (
                        <button disabled={entityMergeLoading} onClick={() => void handleLoadEntityMergeCandidates()} type="button">检查待确认实体</button>
                      ) : null}
                    </div>
                    <section>
                      <h3>业务关系</h3>
                      {crmSelectedRelations.map((edge) => {
                        const otherNodeId = edge.from === selectedGraphNode.id ? edge.to : edge.from;
                        return (
                          <button key={edge.id} onClick={() => setSelectedGraphNodeId(otherNodeId)} type="button">
                            <span>{crmRelationLabel(edge.relation_type)}</span>
                            <strong title={nodeTitleById.get(otherNodeId) || otherNodeId}>{nodeTitleById.get(otherNodeId) || otherNodeId}</strong>
                          </button>
                        );
                      })}
                      {crmSelectedRelations.length === 0 ? <p>暂无已识别关系。</p> : null}
                    </section>
                    <section>
                      <h3>相关互动</h3>
                      {crmSelectedEvents.map((event) => (
                        <button
                          className={selectedGraphEventId === event.id ? "is-selected" : ""}
                          key={event.id}
                          onClick={() => setSelectedGraphEventId(event.id)}
                          type="button"
                        >
                          <span>{event.date || "未标日期"}</span>
                          <strong title={event.title}>{crmShortSource(event.title)}</strong>
                        </button>
                      ))}
                      {crmSelectedEvents.length === 0 ? <p>暂无互动记录。</p> : null}
                    </section>
                    {selectedGraphEvent ? (
                      <section className="crm-intelligence-event-focus">
                        <h3>事件详情</h3>
                        <strong title={selectedGraphEvent.title}>{crmShortSource(selectedGraphEvent.title)}</strong>
                        <span>{selectedGraphEvent.date || "未标日期"}</span>
                        <small>{crmShortSource(selectedGraphEvent.source_file)}</small>
                        <button disabled={!selectedGraphEventSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphEventSourcePath)} type="button">打开事件来源</button>
                      </section>
                    ) : null}
                    {canShowEntityMergeReview ? (
                      <details className="crm-intelligence-admin">
                        <summary>管理员处理</summary>
                        {entityMergeMessage ? <p>{entityMergeMessage}</p> : null}
                        {visibleEntityCandidates.map((candidate) => (
                          <div key={candidate.id}>
                            <strong>{candidate.title}</strong>
                            <span>{crmEntityLabel(candidate.entity_type)} · {Math.round((candidate.confidence ?? 0) * 100)}%</span>
                            <button disabled={entityMergeLoading} onClick={() => void handlePreviewEntityMergeCandidate(candidate)} type="button">预览</button>
                            <button disabled={entityMergeLoading} onClick={() => void handleApplyEntityMergeCandidate(candidate, "dismiss")} type="button">忽略</button>
                          </div>
                        ))}
                        {visibleEntityCandidates.length === 0 ? <button disabled={entityMergeLoading} onClick={() => void handleLoadEntityMergeCandidates()} type="button">加载待确认实体</button> : null}
                      </details>
                    ) : null}
                  </>
                ) : (
                  <p>请选择一个客户、联系人或项目。</p>
                )}
              </aside>
            </div>
          ) : null}
        </section>
      </div>
    ) : null}
    {knowledgeGraphOpen && !filePreview && !isCustomerWorkspace && !standaloneCustomerIntelligence ? (
      <aside className={`workspace-file-preview-sidecar is-knowledge ${previewResizing ? "is-resizing" : ""}`} aria-label={knowledgeGraphLabel}>
        <div
          aria-label="调整图谱面板宽度"
          aria-orientation="vertical"
          className="workspace-file-preview-resize-handle"
          onMouseDown={handlePreviewResizeStart}
          role="separator"
          title="拖动调整图谱面板宽度"
        />
        <header className="workspace-file-preview-sidecar-header">
          <div>
            <strong>{knowledgeGraphLabel}</strong>
            <span>{knowledgeGraph?.source_id || workspaceName || "当前工作区"}</span>
          </div>
          <button aria-label={`关闭${knowledgeGraphLabel}`} className="workspace-file-action" onClick={closeKnowledgeGraph} title="关闭" type="button"><XmarkIcon /></button>
        </header>
        <div className="workspace-knowledge-graph-panel">
          {knowledgeGraphLoading ? <p className="agent-file-panel-note">正在读取 GBrain 图谱...</p> : null}
          {knowledgeGraphError ? <p className="agent-file-panel-note is-error"><span>{knowledgeGraphError}</span><button onClick={() => setKnowledgeGraphError(null)} type="button">关闭</button></p> : null}
          {!knowledgeGraphLoading && knowledgeGraph ? (
            <>
              <div className="workspace-knowledge-graph-stats">
                <span><strong>{knowledgeGraph.stats?.nodes ?? knowledgeGraph.nodes.length}</strong><small>实体</small></span>
                <span><strong>{knowledgeGraph.stats?.edges ?? knowledgeGraph.edges.length}</strong><small>关系</small></span>
                <span><strong>{knowledgeGraph.stats?.events ?? knowledgeGraph.events.length}</strong><small>事件</small></span>
              </div>
              <div className="workspace-knowledge-graph-filters" aria-label="图谱筛选">
                <label>
                  <span>搜索</span>
                  <input
                    onChange={(event) => setGraphSearchTerm(event.target.value)}
                    placeholder="实体、关系、事件或来源"
                    type="search"
                    value={graphSearchTerm}
                  />
                </label>
                <label>
                  <span>类型</span>
                  <select onChange={(event) => setGraphEntityFilter(event.target.value)} value={graphEntityFilter}>
                    <option value="all">全部实体</option>
                    {graphEntityTypes.map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </label>
                {(graphSearchTerm || graphEntityFilter !== "all") ? (
                  <button onClick={() => { setGraphSearchTerm(""); setGraphEntityFilter("all"); }} type="button">重置</button>
                ) : null}
              </div>
              <section className="workspace-knowledge-graph-section">
                <h3>{isCustomerWorkspace ? "画像记忆" : "关键节点"}</h3>
                {filteredProfileCards.length > 0 ? (
                  <div className="workspace-knowledge-card-list">
                    {filteredProfileCards.map((card) => (
                      <article className={`workspace-knowledge-card ${selectedGraphNodeId === card.id ? "is-selected" : ""}`} key={card.id}>
                        <div>
                          <strong>{card.title}</strong>
                          <span>{card.entity_type}</span>
                          <small>{card.relation_count} 条关系 · {card.event_count} 个事件</small>
                        </div>
                        <div className="workspace-knowledge-card-actions">
                          <button onClick={() => setSelectedGraphNodeId(card.id)} type="button">详情</button>
                          <button disabled={nativeGraphLoadingSlug === card.id} onClick={() => void handleLoadNativeGraphContext(card.id)} type="button">
                            {nativeGraphLoadingSlug === card.id ? "读取..." : isCustomerWorkspace ? "支撑信息" : "原生"}
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="workspace-knowledge-empty">暂无可展示的画像节点。</p>
                )}
              </section>
              <section className="workspace-knowledge-graph-section">
                <div className="workspace-knowledge-section-header">
                  <h3>{isCustomerWorkspace ? "关系网" : "事件关系图"}</h3>
                  <div className="workspace-knowledge-section-actions">
                    <small className="workspace-knowledge-section-meta">{canvasGraphNodes.length} 节点 · {canvasGraphEdges.length} 边</small>
                    <button disabled={canvasGraphNodes.length === 0} onClick={() => { resetKnowledgeGraphCanvasView(); setKnowledgeGraphCanvasOpen(true); }} title="打开大画布" type="button">
                      <MaximizeIcon />大画布
                    </button>
                  </div>
                </div>
                {canvasGraphNodes.length > 0 ? (
                  <div className="workspace-knowledge-canvas" aria-label={`${knowledgeGraphLabel}画布`} role="img">
                    <svg viewBox="0 0 340 216" preserveAspectRatio="xMidYMid meet">
                      <defs>
                        <marker id="workspace-graph-arrow" markerHeight="5" markerWidth="6" orient="auto" refX="5" refY="2.5">
                          <path d="M0,0 L6,2.5 L0,5 Z" />
                        </marker>
                      </defs>
                      {canvasGraphEdges.map((edge) => {
                        const from = canvasGraphPositions.get(edge.from);
                        const to = canvasGraphPositions.get(edge.to);
                        if (!from || !to) return null;
                        const isActive = Boolean(selectedGraphNode && (edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id));
                        return (
                          <g className={`workspace-knowledge-canvas-edge ${isActive ? "is-active" : ""}`} key={edge.id}>
                            <line markerEnd="url(#workspace-graph-arrow)" x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
                            <title>{`${nodeTitleById.get(edge.from) || edge.from} -> ${edge.relation_type} -> ${nodeTitleById.get(edge.to) || edge.to}`}</title>
                          </g>
                        );
                      })}
                      {canvasGraphNodes.map((node) => {
                        const point = canvasGraphPositions.get(node.id);
                        if (!point) return null;
                        const isSelected = selectedGraphNodeId === node.id;
                        const degree = graphDegreeById.get(node.id) ?? 0;
                        const maxDegree = Math.max(1, ...canvasGraphNodes.map((n) => graphDegreeById.get(n.id) ?? 0));
                        const degreeRadius = 16 + Math.min(12, (degree / maxDegree) * 12);
                        const nodeRadius = isSelected ? degreeRadius + 4 : degreeRadius;
                        const isNeighbor = selectedNeighborIds.has(node.id);
                        return (
                          <g
                            className={`workspace-knowledge-canvas-node ${isSelected ? "is-selected" : ""} ${isNeighbor ? "is-neighbor" : ""}`}
                            key={node.id}
                            onClick={() => setSelectedGraphNodeId(node.id)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                setSelectedGraphNodeId(node.id);
                              }
                            }}
                            role="button"
                            tabIndex={0}
                            transform={`translate(${point.x} ${point.y})`}
                          >
                            <circle fill={graphEntityTypeColor(node.entity_type)} r={nodeRadius} />
                            <text textAnchor="middle" y="4">{graphCanvasLabel(node.title)}</text>
                            <title>{`${node.title} · ${node.entity_type}`}</title>
                          </g>
                        );
                      })}
                    </svg>
                    <div className="workspace-knowledge-canvas-legend">
                      <span>点击节点查看详情</span>
                      {selectedGraphNode ? <strong title={selectedGraphNode.title}>{selectedGraphNode.title}</strong> : null}
                    </div>
                  </div>
                ) : (
                  <p className="workspace-knowledge-empty">暂无可绘制的图谱节点。</p>
                )}
              </section>
              {selectedGraphNode ? (
                <section className="workspace-knowledge-graph-section">
                  <div className="workspace-knowledge-section-header">
                    <h3>节点详情</h3>
                    <div className="workspace-knowledge-section-actions">
                      <button disabled={!selectedGraphNodeSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphNodeSourcePath)} type="button">来源</button>
                      <button disabled={nativeGraphLoadingSlug === selectedGraphNode.id} onClick={() => void handleLoadNativeGraphContext(selectedGraphNode.id)} type="button">
                        {nativeGraphLoadingSlug === selectedGraphNode.id ? "读取..." : isCustomerWorkspace ? "读取支撑信息" : "读取原生上下文"}
                      </button>
                    </div>
                  </div>
                  <article className="workspace-knowledge-node-detail">
                    <div>
                      <strong>{selectedGraphNode.title}</strong>
                      <span>{[selectedGraphNode.entity_type, selectedGraphNode.source_file || selectedGraphNode.file].filter(Boolean).join(" · ")}</span>
                      {selectedGraphNodeSourcePath ? <small>可预览来源：{selectedGraphNodeSourcePath}</small> : <small>citation：{graphCitationString(selectedGraphNode.citation, "file") || selectedGraphNode.file}</small>}
                    </div>
                    {selectedGraphNodeEdges.length ? (
                      <div>
                        <small>关联关系</small>
                        {selectedGraphNodeEdges.map((edge) => {
                          const otherNodeId = edge.from === selectedGraphNode.id ? edge.to : edge.from;
                          return (
                            <button key={edge.id} onClick={() => setSelectedGraphNodeId(otherNodeId)} type="button">
                              {edge.relation_type} · {nodeTitleById.get(otherNodeId) || otherNodeId}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                    {selectedGraphNodeEvents.length ? (
                      <div>
                        <small>关联事件</small>
                        {selectedGraphNodeEvents.map((event) => (
                          <button key={event.id} onClick={() => setSelectedGraphEventId(event.id)} type="button">
                            {[event.date, event.title, event.source_file].filter(Boolean).join(" · ")}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                </section>
              ) : null}
              <section className="workspace-knowledge-graph-section">
                <h3>关系</h3>
                {filteredGraphEdges.slice(0, 10).map((edge) => (
                  <div className="workspace-knowledge-relation-row" key={edge.id}>
                    <button title={edge.from} onClick={() => setSelectedGraphNodeId(edge.from)} type="button">{nodeTitleById.get(edge.from) || edge.from}</button>
                    <small>{edge.relation_type}</small>
                    <button title={edge.to} onClick={() => setSelectedGraphNodeId(edge.to)} type="button">{nodeTitleById.get(edge.to) || edge.to}</button>
                  </div>
                ))}
                {filteredGraphEdges.length === 0 ? <p className="workspace-knowledge-empty">暂无匹配的关系边。</p> : null}
              </section>
              <section className="workspace-knowledge-graph-section">
                <div className="workspace-knowledge-section-header">
                  <h3>Timeline</h3>
                  <div className="workspace-knowledge-timeline-filter" aria-label="Timeline 筛选">
                    {[
                      { key: "all", label: "全部" },
                      { key: "dated", label: "有日期" },
                      { key: "undated", label: "未标日期" },
                      { key: "selected", label: "当前节点" },
                    ].map((item) => (
                      <button
                        aria-pressed={graphTimelineFilter === item.key}
                        className={graphTimelineFilter === item.key ? "is-active" : ""}
                        disabled={item.key === "selected" && !selectedGraphNode}
                        key={item.key}
                        onClick={() => setGraphTimelineFilter(item.key as typeof graphTimelineFilter)}
                        type="button"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                  <div className="workspace-knowledge-timeline-tools" aria-label="Timeline 显示控制">
                    <button
                      aria-pressed={graphTimelineDensity === "compact"}
                      className={graphTimelineDensity === "compact" ? "is-active" : ""}
                      onClick={() => setGraphTimelineDensity((value) => (value === "compact" ? "detail" : "compact"))}
                      type="button"
                    >
                      {graphTimelineDensity === "compact" ? "紧凑" : "详细"}
                    </button>
                    <button
                      aria-pressed={graphTimelineDensity === "axis"}
                      className={graphTimelineDensity === "axis" ? "is-active" : ""}
                      onClick={() => setGraphTimelineDensity((value) => (value === "axis" ? "detail" : "axis"))}
                      title="时间轴模式：以可视化时间线排列事件"
                      type="button"
                    >
                      时间轴
                    </button>
                    <button disabled={timelineGroups.length === 0} onClick={() => collapseAllTimelineGroups(timelineGroupLabels)} type="button">
                      折叠
                    </button>
                    <button disabled={collapsedTimelineGroups.size === 0} onClick={expandAllTimelineGroups} type="button">
                      展开
                    </button>
                  </div>
                </div>
                {(graphTimelineDensity === "axis" && timelineGroups.length > 0) ? (
                <div className="workspace-knowledge-timeline-axis" aria-label="Timeline 时间轴">
                  <div className="workspace-knowledge-timeline-axis-line" />
                  {timelineGroups
                    .filter((group) => group.label !== "未标日期")
                    .flatMap((group) => group.events.map((event) => ({ ...event, groupLabel: group.label })))
                    .sort((a, b) => (graphEventTimestamp(a.date) ?? 0) - (graphEventTimestamp(b.date) ?? 0))
                    .slice(0, 30)
                    .map((event, idx, arr) => {
                      const ts = graphEventTimestamp(event.date);
                      const minTs = graphEventTimestamp(arr[0].date) ?? ts ?? Date.now();
                      const maxTs = graphEventTimestamp(arr[arr.length - 1].date) ?? ts ?? Date.now();
                      const range = Math.max(1, (maxTs ?? minTs ?? 0) - (minTs ?? 0));
                      const offset = range > 0 ? ((ts ?? minTs ?? 0) - (minTs ?? 0)) / range : 0.5;
                      const leftPct = Math.max(2, Math.min(98, offset * 100));
                      const isSelected = selectedGraphEventId === event.id;
                      const nodeTitle = nodeTitleById.get(event.entity_id) || "";
                      return (
                        <div
                          className={`workspace-knowledge-timeline-axis-point ${isSelected ? "is-selected" : ""}`}
                          key={event.id}
                          onClick={() => setSelectedGraphEventId(event.id)}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedGraphEventId(event.id); } }}
                          role="button"
                          style={{ left: `${leftPct}%` }}
                          tabIndex={0}
                          title={`${event.date || "无日期"} · ${event.title} · ${nodeTitle}`}
                        >
                          <div className="workspace-knowledge-timeline-axis-dot" />
                          <div className="workspace-knowledge-timeline-axis-label">
                            <span>{event.date}</span>
                            <strong>{graphCanvasLabel(event.title)}</strong>
                            {nodeTitle ? <small>{nodeTitle}</small> : null}
                          </div>
                        </div>
                      );
                    })}
                  {timelineGroups.filter((group) => group.label === "未标日期").length > 0 ? (
                    <div className="workspace-knowledge-timeline-axis-undated">
                      <span>+{timelineGroups.filter((group) => group.label === "未标日期").reduce((sum, g) => sum + g.events.length, 0)} 个未标日期事件</span>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {timelineGroups.map((group) => (
                  <div className={`workspace-knowledge-timeline-group ${collapsedTimelineGroups.has(group.label) ? "is-collapsed" : ""}`} key={group.label}>
                    <div className="workspace-knowledge-timeline-date">
                      <button
                        aria-expanded={!collapsedTimelineGroups.has(group.label)}
                        onClick={() => toggleTimelineGroup(group.label)}
                        type="button"
                      >
                        <span>{group.label}</span>
                        <small>{collapsedTimelineGroups.has(group.label) ? "已折叠" : `${group.events.length} 个事件`}</small>
                      </button>
                    </div>
                    <div className={`workspace-knowledge-timeline-items is-${graphTimelineDensity}`}>
                      {group.events.map((event) => (
                        <button
                          className={`workspace-knowledge-event-row ${selectedGraphEventId === event.id ? "is-selected" : ""} ${graphTimelineDensity === "compact" ? "is-compact" : ""}`}
                          key={event.id}
                          onClick={() => {
                            setSelectedGraphNodeId(event.entity_id);
                            setSelectedGraphEventId(event.id);
                          }}
                          type="button"
                        >
                          <strong>{event.title}</strong>
                          <span>{[event.date, nodeTitleById.get(event.entity_id) || event.entity_id, event.source_file].filter(Boolean).join(" · ")}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                {timelineHiddenCount > 0 ? <p className="workspace-knowledge-empty">当前密度下隐藏 {timelineHiddenCount} 个事件，可切换紧凑显示更多。</p> : null}
                {timelineGroups.length === 0 ? <p className="workspace-knowledge-empty">{knowledgeGraph.warnings?.[0] || "暂无匹配的事件记录。"}</p> : null}
              </section>
              {selectedGraphEvent ? (
                <section className="workspace-knowledge-graph-section">
                  <div className="workspace-knowledge-section-header">
                    <h3>事件详情</h3>
                    <div className="workspace-knowledge-section-actions">
                      <button disabled={!selectedGraphEventSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphEventSourcePath)} type="button">来源</button>
                      <button onClick={() => setSelectedGraphEventId(null)} type="button">清除</button>
                    </div>
                  </div>
                  <article className="workspace-knowledge-event-detail">
                    <strong>{selectedGraphEvent.title}</strong>
                    <span>{[selectedGraphEvent.date || "未标日期", nodeTitleById.get(selectedGraphEvent.entity_id) || selectedGraphEvent.entity_id].filter(Boolean).join(" · ")}</span>
                    {selectedGraphEvent.source_file ? <small>来源：{selectedGraphEvent.source_file}</small> : null}
                    {selectedGraphEventSourcePath ? <small>可预览来源：{selectedGraphEventSourcePath}</small> : null}
                    {selectedGraphEvent.citation ? (
                      <small title={JSON.stringify(selectedGraphEvent.citation)}>citation：{graphCitationString(selectedGraphEvent.citation, "file") || "已绑定"}</small>
                    ) : (
                      <small>暂无 citation。</small>
                    )}
                  </article>
                </section>
              ) : null}
              {(nativeGraphContext || nativeGraphMessage) ? (
                <section className="workspace-knowledge-graph-section">
                  <h3>{isCustomerWorkspace ? "客户情报支撑信息" : "GBrain 原生上下文"}</h3>
                  {nativeGraphMessage ? <p className="workspace-knowledge-empty">{nativeGraphMessage}</p> : null}
                  {nativeGraphContext && nativeCounts ? (
                    <div className="workspace-native-context-card">
                      <strong title={nativeGraphContext.slug}>{nativeGraphContext.slug}</strong>
                      <span>{nativeGraphContext.source_id || knowledgeGraph.source_id}</span>
                      <small>graph {nativeCounts.traverse} · timeline {nativeCounts.timeline} · backlinks {nativeCounts.backlinks}</small>
                    </div>
                  ) : null}
                  {nativeContextSections.map((section) => (
                    <div className="workspace-native-context-section" key={section.key}>
                      <div>
                        <strong>{section.title}</strong>
                        <small>{section.items.length} shown</small>
                      </div>
                      {section.items.length > 0 ? section.items.map((item) => (
                        <article className="workspace-native-context-row" key={item.id}>
                          <strong title={item.title}>{item.title}</strong>
                          <span title={item.subtitle}>{item.subtitle}</span>
                          {item.detail ? <small title={item.detail}>{item.detail}</small> : null}
                        </article>
                      )) : (
                        <p className="workspace-knowledge-empty">暂无 {section.title} 明细。</p>
                      )}
                    </div>
                  ))}
                </section>
              ) : null}
              {canShowEntityMergeReview ? (
                <section className="workspace-knowledge-graph-section">
                  <div className="workspace-knowledge-section-header">
                    <h3>实体候选</h3>
                    <button disabled={entityMergeLoading} onClick={() => void handleLoadEntityMergeCandidates()} type="button">
                      {entityMergeLoading ? "处理中..." : "加载"}
                    </button>
                  </div>
                  {entityMergeMessage ? <p className="workspace-knowledge-empty">{entityMergeMessage}</p> : null}
                  {visibleEntityCandidates.map((candidate) => {
                    const targets = (candidate.target_nodes ?? []).map((node) => node.title).filter(Boolean).join(", ");
                    const evidence = (candidate.evidence_edges ?? []).map((edge) => edge.evidence).filter(Boolean).join(", ");
                    const canCreate = candidate.suggested_action === "create_entity_page" || candidate.suggested_action === "create_event_page";
                    const canRecordAlias = candidate.suggested_action === "merge_duplicate_pages" || candidate.suggested_action === "link_to_existing_entity";
                    return (
                      <article className="workspace-knowledge-candidate-card" key={candidate.id}>
                        <div>
                          <strong>{candidate.title}</strong>
                          <span>{candidate.candidate_type} · {candidate.suggested_action}</span>
                          <small>{targets || evidence || candidate.reason || "需要人工判断"}</small>
                        </div>
                        <div>
                          <button disabled={entityMergeLoading || !canCreate} onClick={() => void handleApplyEntityMergeCandidate(candidate, "create_entity_page")} type="button">建档</button>
                          <button disabled={entityMergeLoading || !canRecordAlias} onClick={() => void handlePreviewEntityMergeCandidate(candidate)} type="button">预览</button>
                          <button disabled={entityMergeLoading || !canRecordAlias} onClick={() => void handleApplyEntityMergeCandidate(candidate, "record_alias")} type="button">别名</button>
                          <button disabled={entityMergeLoading || !canRecordAlias} onClick={() => void handleApplyEntityMergeCandidate(candidate, "apply_relink_changes")} type="button">改写</button>
                          <button disabled={entityMergeLoading} onClick={() => void handleApplyEntityMergeCandidate(candidate, "dismiss")} type="button">忽略</button>
                        </div>
                      </article>
                    );
                  })}
                  {entityMergePreview ? (
                    <article className="workspace-knowledge-merge-preview">
                      <div>
                        <strong>合并预览</strong>
                        <span>{entityMergePreview.planned_alias_review_file || "未生成 alias 文件路径"}</span>
                      </div>
                      <small>
                        主实体：{entityMergePreview.canonical_entity?.title || "-"} · 别名：{(entityMergePreview.alias_entities ?? []).map((node) => node.title).join(", ") || "-"}
                      </small>
                      {(entityMergePreview.planned_relink_changes ?? []).slice(0, 5).map((change) => (
                        <p key={`${change.page_id}-${change.field}-${change.index}`}>
                          <span>{change.page_title}</span>
                          <code>{change.diff_preview}</code>
                        </p>
                      ))}
                      {(entityMergePreview.planned_relink_changes ?? []).length === 0 ? <small>未发现需要自动改写的 frontmatter 引用。</small> : null}
                    </article>
                  ) : null}
                  {entityMergeCandidates && visibleEntityCandidates.length === 0 ? <p className="workspace-knowledge-empty">暂无实体候选。</p> : null}
                </section>
              ) : null}
            </>
          ) : null}
        </div>
      </aside>
    ) : null}
    {knowledgeGraphCanvasOpen && knowledgeGraph ? (
      <div className="workspace-knowledge-map-overlay" role="dialog" aria-modal="true" aria-label={`${knowledgeGraphLabel}大画布`}>
        <section className="workspace-knowledge-map-shell">
          <header className="workspace-knowledge-map-header">
            <div>
              <span>{knowledgeGraph.source_id || workspaceName || "当前工作区"}</span>
              <strong>{knowledgeGraphLabel}大画布</strong>
            </div>
            <div className="workspace-knowledge-map-header-actions">
              <small>{largeGraphNodes.length} 节点 · {largeGraphEdges.length} 边 · {filteredGraphEvents.length} 事件</small>
              <button aria-label="缩小图谱" onClick={() => zoomKnowledgeGraphCanvas(-0.16)} title="缩小" type="button">-</button>
              <button aria-label="重置图谱视图" onClick={resetKnowledgeGraphCanvasView} title="重置视图" type="button">{Math.round(knowledgeGraphCanvasView.scale * 100)}%</button>
              <button aria-label="放大图谱" onClick={() => zoomKnowledgeGraphCanvas(0.16)} title="放大" type="button">+</button>
              <button aria-label="关闭大画布" onClick={() => setKnowledgeGraphCanvasOpen(false)} title="关闭" type="button"><XmarkIcon /></button>
            </div>
          </header>
          <div className="workspace-knowledge-map-content">
            <div
              className={`workspace-knowledge-map-canvas ${knowledgeGraphCanvasPanning ? "is-panning" : ""}`}
              onMouseDown={handleKnowledgeGraphCanvasPanStart}
              onWheel={handleKnowledgeGraphCanvasWheel}
            >
              <svg viewBox="0 0 960 560" preserveAspectRatio="xMidYMid meet">
                <defs>
                  <marker id="workspace-graph-large-arrow" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
                    <path d="M0,0 L7,3 L0,6 Z" />
                  </marker>
                </defs>
                <g transform={`translate(${knowledgeGraphCanvasView.x} ${knowledgeGraphCanvasView.y}) scale(${knowledgeGraphCanvasView.scale})`}>
                  {largeGraphEdges.map((edge) => {
                    const from = largeGraphPositions.get(edge.from);
                    const to = largeGraphPositions.get(edge.to);
                    if (!from || !to) return null;
                    const isActive = Boolean(selectedGraphNode && (edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id));
                    return (
                      <g className={`workspace-knowledge-map-edge ${isActive ? "is-active" : ""}`} key={edge.id}>
                        <line markerEnd="url(#workspace-graph-large-arrow)" x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
                        <title>{`${nodeTitleById.get(edge.from) || edge.from} -> ${isCustomerWorkspace ? crmRelationLabel(edge.relation_type) : edge.relation_type} -> ${nodeTitleById.get(edge.to) || edge.to}`}</title>
                      </g>
                    );
                  })}
                  {largeGraphNodes.map((node) => {
                    const point = largeGraphPositions.get(node.id);
                    if (!point) return null;
                    const degree = graphDegreeById.get(node.id) ?? 0;
                    const radius = Math.max(20, Math.min(34, 20 + degree * 2));
                    const isSelected = selectedGraphNodeId === node.id;
                    const isNeighbor = selectedNeighborIds.has(node.id);
                    return (
                      <g
                        className={`workspace-knowledge-map-node ${isSelected ? "is-selected" : ""} ${isNeighbor ? "is-neighbor" : ""}`}
                        key={node.id}
                        onClick={() => setSelectedGraphNodeId(node.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedGraphNodeId(node.id);
                          }
                        }}
                        role="button"
                        tabIndex={0}
                        transform={`translate(${point.x} ${point.y})`}
                      >
                        <circle r={isSelected ? radius + 4 : radius} />
                        <text textAnchor="middle" y="-2">{graphCanvasLargeLabel(node.title)}</text>
                        <text className="workspace-knowledge-map-node-type" textAnchor="middle" y="13">{isCustomerWorkspace ? crmEntityLabel(node.entity_type) : node.entity_type || "entity"}</text>
                        <title>{`${node.title} · ${isCustomerWorkspace ? crmEntityLabel(node.entity_type) : node.entity_type || "entity"} · ${degree} 条关系`}</title>
                      </g>
                    );
                  })}
                </g>
              </svg>
              <div className="workspace-knowledge-map-legend">
                <span>滚轮缩放，拖动画布空白处平移</span>
                <span>点击节点后，右侧详情与侧栏详情同步</span>
              </div>
            </div>
            <aside className="workspace-knowledge-map-inspector">
              {selectedGraphNode ? (
                <>
                  <section>
                    <small>当前节点</small>
                    <strong>{selectedGraphNode.title}</strong>
                    <span>{[isCustomerWorkspace ? crmEntityLabel(selectedGraphNode.entity_type) : selectedGraphNode.entity_type, selectedGraphNode.source_file || selectedGraphNode.file].filter(Boolean).join(" · ") || "未标来源"}</span>
                    <button disabled={!selectedGraphNodeSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphNodeSourcePath)} type="button">
                      <span>Source preview</span>
                      <strong>{selectedGraphNodeSourcePath || "无可预览来源"}</strong>
                    </button>
                  </section>
                  <section>
                    <small>关联关系</small>
                    {selectedGraphNodeEdges.length ? selectedGraphNodeEdges.map((edge) => {
                      const otherNodeId = edge.from === selectedGraphNode.id ? edge.to : edge.from;
                      return (
                        <button key={edge.id} onClick={() => setSelectedGraphNodeId(otherNodeId)} type="button">
                          <span>{isCustomerWorkspace ? crmRelationLabel(edge.relation_type) : edge.relation_type}</span>
                          <strong>{nodeTitleById.get(otherNodeId) || otherNodeId}</strong>
                        </button>
                      );
                    }) : <p>当前筛选下暂无关系。</p>}
                  </section>
                  <section>
                    <small>相关事件</small>
                    {selectedGraphNodeEvents.length ? selectedGraphNodeEvents.map((event) => (
                      <div className="workspace-knowledge-map-event-card" key={event.id}>
                        <button onClick={() => { setSelectedGraphEventId(event.id); setGraphTimelineFilter("selected"); }} type="button">
                          <span>{event.date || "未标日期"}</span>
                          <strong>{event.title}</strong>
                        </button>
                        <button disabled={!graphPreviewSourcePath(event)} onClick={() => void openGraphSourcePreview(graphPreviewSourcePath(event))} type="button">
                          <span>来源</span>
                          <strong>{graphPreviewSourcePath(event) || "无可预览来源"}</strong>
                        </button>
                      </div>
                    )) : <p>暂无事件。</p>}
                  </section>
                </>
              ) : (
                <section>
                  <small>未选择节点</small>
                  <p>点击画布中的实体节点查看关系和事件。</p>
                </section>
              )}
            </aside>
          </div>
        </section>
      </div>
    ) : null}
    </div>
  );
}
