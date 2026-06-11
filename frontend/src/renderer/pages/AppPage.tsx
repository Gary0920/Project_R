import { ClipboardEvent, DragEvent, KeyboardEvent, MouseEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";

import { ApiError, type ApiClientOptions } from "../shared/api/client";
import {
  activateChatMessageVersion,
  archiveChatSession,
  createSessionAttachment,
  createChatSession,
  deleteChatMessage,
  deleteSessionAttachment,
  deleteChatSession,
  editChatMessage,
  fetchSessionAttachmentBlob,
  listChatMessages,
  listChatSessions,
  regenerateChatMessage,
  restoreDeletedChatMessages,
  searchChatSessions,
  sendChatMessage,
  submitGBrainThinkReview,
  submitMessageFeedback,
  updateChatSession,
  uploadSessionAttachmentFile,
} from "../features/chat/api";
import { getLLMHealth } from "../shared/api/health";
import {
  getNotificationCounts,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationView,
  updateNotificationActionStatus,
} from "../features/notifications/api";
import { listCompanyPrompts } from "../features/prompts/api";
import { listSkills } from "../features/skills/api";
import { getLatestClientUpdate } from "../features/updates/api";
import { fetchWorkspaceFileBlob } from "../features/workspace/api";
import { authTokenAtom, clearAuthAtom, currentUserAtom } from "../features/auth/state";
import { parseApiDate } from "../shared/utils/time";
import {
  activeMessagesAtom,
  activeSessionAtom,
  activeSessionIdAtom,
  chatErrorAtom,
  chatLoadingAtom,
  chatMessagesBySessionAtom,
  chatSessionsAtom,
  type ChatMessage,
} from "../features/chat/state";
import { serverUrlAtom } from "../shared/state/server";
import { activeModeAtom } from "../shared/state/ui";
import { activeTabIdAtom, tabsAtom } from "../features/chat/tabs-state";
import { activeWorkspaceIdAtom, workspacesAtom } from "../features/workspace/state";
import { notificationsAtom, pendingNotificationCountAtom, unreadNotificationCountAtom } from "../features/notifications/state";
import {
  formatNotificationTime,
  notificationCategoryLabel,
  numericPayloadValue,
  shouldToastNotification,
  stringPayloadValue,
} from "../features/notifications/formatters";
import type {
  ChatSearchResultResponse,
  ChatSessionResponse,
  ChatMessageVersionResponse,
  ChatContextTraceResponse,
  ChatSourceResponse,
  AgentRunResponse,
  ClientUpdateInfo,
  CompanyPromptResponse,
  GeneratedFileResponse,
  LLMProviderStatusResponse,
  NotificationResponse,
  SendChatMessageResponse,
  SessionAttachmentResponse,
  SkillResponse,
  SkillRunResponse,
  WorkspaceFileItemResponse,
} from "../shared/api/types";
import { APP_NAME } from "../shared/config/app";
import { useContextMenu, type ContextMenuItemDef } from "../shared/components/ContextMenu";
import { getPromptOptionId, PromptPanel, type PromptOption } from "../features/prompts/components/PromptPanel";
import { ScratchPad } from "../features/chat/components/ScratchPad";
import { SearchDialog } from "../features/chat/components/SearchDialog";
import { SettingsModal } from "../features/settings/components/SettingsModal";
import { TabBar } from "../features/chat/components/TabBar";
import { WorkspaceSelector } from "../features/workspace/components/WorkspaceSelector";
import { WorkspaceFilePanel } from "../features/workspace/components/WorkspaceFilePanel";
import { copyText, downloadGeneratedFile } from "../features/chat/components/ChatMessageList";
import { AppWorkspaceChrome } from "../features/chat/components/AppWorkspaceChrome";
import { ChatConversationPane } from "../features/chat/components/ChatConversationPane";
import {
  SESSION_ATTACHMENT_MAX_BYTES,
  attachmentSourceLabel,
  fileFromPrivateWorkspacePayload,
  filesFromClipboard,
  formatAttachmentSize,
  getAttachmentKind,
  hasFileTransfer,
  hashFileSha256,
  isAudioTranscriptionRequest,
  isAudioVideoAttachment,
  isLocalPrivatePendingAttachment,
  isUploadedPendingAttachment,
  makeLocalAttachmentId,
  pendingAttachmentKey,
  pendingAttachmentSendFormLabel,
  pendingAttachmentStatusLabel,
  pendingAttachmentTargetLabel,
  readTextAttachmentExcerpt,
  type AttachmentAuthorizationStatus,
  type AttachmentInputSource,
  type PendingSessionAttachment,
} from "../features/chat/attachments";
import {
  FALLBACK_CLIENT_VERSION,
  UPDATE_DOWNLOAD_DRY_RUN,
  compareClientVersions,
  formatUpdateBytes,
  formatUpdateSpeed,
  resolveCurrentClientVersion,
} from "../features/updates/clientVersion";
import {
  formatClockTime,
  formatSessionDisplayTitle,
  formatSidebarTime,
  getInitials,
  groupSessionsByTime,
  makeSessionTitle,
  renderAvatar,
  resolveAvatarUrl,
} from "../features/chat/sessionDisplay";
import {
  BUILTIN_SLASH_COMMANDS,
  findSlashCommand,
  getSkillScopeLabel,
  scoreBuiltinSlashCommand,
  scoreSkill,
  type BuiltinSlashCommand,
  type SkillSlashCandidate,
  type SlashCommandMatch,
} from "../features/chat/slashCommands";
import { PROJECT_R_BUILTIN_PROMPT } from "../features/prompts/constants";
type SplitPaneKey = "left" | "right";
type UtilityPanel = "workspace" | "customer-intelligence" | "prompt" | "skills" | "source" | "crm";
type RenameScope = "header" | "sidebar";
type SettingsAdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type ClientUpdateStep = "available" | "downloading" | "installing" | "ready" | "failed";
type SourcePreview = {
  index: number;
  source: ChatSourceResponse;
  sessionId?: number | null;
};

type ModelOption = {
  key: string;
  label: string;
  provider: string;
  profile: string;
  description: string;
  model: string;
  supportsVision: boolean;
  isDefault: boolean;
};

const PROMPT_SELECTION_KEY = "project_r_session_prompt_selection";
const SETTINGS_PREFERENCES_KEY = "project-r:settings-preferences";
const SIDEBAR_WIDTH_KEY = "project-r:chat-sidebar-width";
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_DEFAULT_WIDTH = 268;
const SIDEBAR_MAX_WIDTH = 420;
const WORKSPACE_PANEL_WIDTH_KEY = "project-r:workspace-panel-width";
const WORKSPACE_PANEL_MIN_WIDTH = 320;
const WORKSPACE_PANEL_DEFAULT_WIDTH = 480;
const WORKSPACE_PANEL_PREVIEW_WIDTH = 720;
const WORKSPACE_PANEL_MAX_WIDTH = 880;
const AUXILIARY_PANEL_WIDTH_KEY = "project-r:auxiliary-side-panel-width";
const AUXILIARY_PANEL_MIN_WIDTH = 300;
const AUXILIARY_PANEL_DEFAULT_WIDTH = 380;
const AUXILIARY_PANEL_MAX_WIDTH = 720;
const MODEL_COPY: Record<string, { label: string; description: string }> = {
  deepseek: { label: "DeepSeek", description: "文本对话、推理输出" },
  claude: { label: "Claude", description: "复杂推理与长文处理" },
  openai: { label: "OpenAI", description: "通用兼容接口" },
  mimo: { label: "MiMo", description: "多模态理解" },
};

const MODEL_CAPABILITY_COPY: Record<string, string> = {
  "deepseek-flash": "文本对话、快速推理",
  "deepseek-pro": "文本对话、复杂推理",
  "mimo-v2-5": "文本/图像/视频/音频理解",
  "mimo-v2-5-pro": "文本/图像理解，复杂推理",
};

function toModelOption(status: LLMProviderStatusResponse): ModelOption {
  const profile = status.profile ?? status.provider;
  const copy = MODEL_COPY[status.provider] ?? {
    label: status.provider.toUpperCase(),
    description: "已配置模型接口",
  };
  const normalizedModel = status.model.toLowerCase().replace(/\./g, "-");
  const capabilityDescription = MODEL_CAPABILITY_COPY[profile] ?? MODEL_CAPABILITY_COPY[normalizedModel];
  const supportsVision = status.supports_vision ?? Boolean(capabilityDescription?.includes("图像"));
  return {
    key: profile,
    profile,
    provider: status.provider,
    label: status.label || copy.label,
    description: capabilityDescription || status.description || copy.description,
    model: status.model,
    supportsVision,
    isDefault: status.default,
  };
}
const AGENT_MODE_PROMPT = (
  "当前用户已切换到 Agent 模式。请更积极地承接执行型任务："
  + "当请求涉及文件生成、套模板、业务 Skill、多步骤流程、项目资料核对或可下载输出时，"
  + "优先推进执行、追问必要字段，并避免只给泛泛说明。"
);
const AGENT_SUGGESTION_KEYWORDS = [
  "excel",
  "xlsx",
  "ppt",
  "pptx",
  "模板",
  "套用",
  "skill",
  "流程",
  "审批",
  "审计",
  "项目",
  "资料",
  "文件夹",
  "读取",
  "核对",
  "批量",
  "多步骤",
  "生成表格",
  "项目资料",
];

function readPromptSelectionMap() {
  try {
    return JSON.parse(localStorage.getItem(PROMPT_SELECTION_KEY) ?? "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

function readWebSearchPreference() {
  try {
    const preferences = JSON.parse(localStorage.getItem(SETTINGS_PREFERENCES_KEY) ?? "{}") as { webSearchEnabled?: unknown };
    return preferences.webSearchEnabled === true;
  } catch {
    return false;
  }
}

function writeWebSearchPreference(enabled: boolean) {
  try {
    const preferences = JSON.parse(localStorage.getItem(SETTINGS_PREFERENCES_KEY) ?? "{}");
    localStorage.setItem(SETTINGS_PREFERENCES_KEY, JSON.stringify({ ...preferences, webSearchEnabled: enabled }));
  } catch {
    localStorage.setItem(SETTINGS_PREFERENCES_KEY, JSON.stringify({ webSearchEnabled: enabled }));
  }
}

function sidebarMaxWidth() {
  if (typeof window === "undefined") return SIDEBAR_MAX_WIDTH;
  return Math.max(SIDEBAR_MIN_WIDTH, Math.min(SIDEBAR_MAX_WIDTH, window.innerWidth - 640));
}

function clampSidebarWidth(value: number) {
  return Math.min(sidebarMaxWidth(), Math.max(SIDEBAR_MIN_WIDTH, Math.round(value)));
}

function readSidebarWidth() {
  try {
    const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY));
    return Number.isFinite(stored) ? clampSidebarWidth(stored) : SIDEBAR_DEFAULT_WIDTH;
  } catch {
    return SIDEBAR_DEFAULT_WIDTH;
  }
}

function writeSidebarWidth(width: number) {
  try {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

function workspacePanelMaxWidth() {
  if (typeof window === "undefined") return WORKSPACE_PANEL_MAX_WIDTH;
  return Math.max(WORKSPACE_PANEL_MIN_WIDTH, Math.min(WORKSPACE_PANEL_MAX_WIDTH, window.innerWidth - 420));
}

function clampWorkspacePanelWidth(value: number) {
  return Math.min(workspacePanelMaxWidth(), Math.max(WORKSPACE_PANEL_MIN_WIDTH, Math.round(value)));
}

function readWorkspacePanelWidth() {
  try {
    const stored = Number(localStorage.getItem(WORKSPACE_PANEL_WIDTH_KEY));
    return Number.isFinite(stored) ? clampWorkspacePanelWidth(stored) : clampWorkspacePanelWidth(WORKSPACE_PANEL_DEFAULT_WIDTH);
  } catch {
    return clampWorkspacePanelWidth(WORKSPACE_PANEL_DEFAULT_WIDTH);
  }
}

function writeWorkspacePanelWidth(width: number) {
  try {
    localStorage.setItem(WORKSPACE_PANEL_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

function auxiliaryPanelMaxWidth() {
  if (typeof window === "undefined") return AUXILIARY_PANEL_MAX_WIDTH;
  return Math.max(AUXILIARY_PANEL_MIN_WIDTH, Math.min(AUXILIARY_PANEL_MAX_WIDTH, window.innerWidth - 420));
}

function clampAuxiliaryPanelWidth(value: number) {
  return Math.min(auxiliaryPanelMaxWidth(), Math.max(AUXILIARY_PANEL_MIN_WIDTH, Math.round(value)));
}

function readAuxiliaryPanelWidth() {
  try {
    const stored = Number(localStorage.getItem(AUXILIARY_PANEL_WIDTH_KEY));
    return Number.isFinite(stored) ? clampAuxiliaryPanelWidth(stored) : clampAuxiliaryPanelWidth(AUXILIARY_PANEL_DEFAULT_WIDTH);
  } catch {
    return clampAuxiliaryPanelWidth(AUXILIARY_PANEL_DEFAULT_WIDTH);
  }
}

function writeAuxiliaryPanelWidth(width: number) {
  try {
    localStorage.setItem(AUXILIARY_PANEL_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

function makePromptId(source: PromptOption["source"], id: string) {
  return `${source}:${id}`;
}

function composeSystemPrompt(basePrompt: string, mode: "chat" | "agent") {
  if (mode !== "agent") return basePrompt;
  return [basePrompt, AGENT_MODE_PROMPT].filter(Boolean).join("\n\n");
}

function shouldSuggestAgentMode(
  request: string,
  response: SendChatMessageResponse,
  mode: "chat" | "agent",
) {
  if (mode === "agent") return null;
  if (response.generated_file) return null;
  if (response.skill_run) {
    return "已识别为业务执行任务，Agent 模式更适合补参、调用 Skill 并跟踪输出。";
  }
  const normalized = request.trim().toLowerCase();
  const asksForComplexOutput = AGENT_SUGGESTION_KEYWORDS.some((keyword) => normalized.includes(keyword));
  if (asksForComplexOutput) {
    return "这个请求可能需要读取资料、套模板或执行多步骤流程，建议交给 Agent 模式承接。";
  }
  if (response.intent === "document_generation" && !response.generated_file) {
    return "这个文件生成请求没有返回下载文件，建议切换 Agent 模式继续处理。";
  }
  return null;
}

export function createApiOptions(
  baseUrl: string,
  token: string | null,
  onUnauthorized: () => void,
) {
  return { baseUrl, token, onUnauthorized };
}

function makeLocalMessage(
  sessionId: number,
  role: "user" | "assistant",
  content: string,
  extras: Partial<ChatMessage> = {},
): ChatMessage {
  const now = new Date().toISOString();
  return {
    id: -Date.now() - Math.floor(Math.random() * 1000),
    session_id: sessionId,
    role,
    content,
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
    version_index: 1,
    version_count: 1,
    active_version: true,
    versions: [],
    feedback_rating: null,
    feedback_comment: null,
    sources: [],
    attachments: [],
    agent_run: null,
    context_trace: null,
    created_at: now,
    ...extras,
  };
}

export function AppPage() {
  const serverUrl = useAtomValue(serverUrlAtom);
  const token = useAtomValue(authTokenAtom);
  const currentUser = useAtomValue(currentUserAtom);
  const clearAuth = useSetAtom(clearAuthAtom);
  const [sessions, setSessions] = useAtom(chatSessionsAtom);
  const [activeSessionId, setActiveSessionId] = useAtom(activeSessionIdAtom);
  const activeSession = useAtomValue(activeSessionAtom);
  const activeMessages = useAtomValue(activeMessagesAtom);
  const [messagesBySession, setMessagesBySession] = useAtom(chatMessagesBySessionAtom);
  const [isLoading, setIsLoading] = useAtom(chatLoadingAtom);
  const [error, setError] = useAtom(chatErrorAtom);
  const [actionNotice, setActionNotice] = useState("");
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useAtom(activeModeAtom);
  const [tabs, setTabs] = useAtom(tabsAtom);
  const [activeTabId, setActiveTabId] = useAtom(activeTabIdAtom);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(readWebSearchPreference);
  const [activeWorkspaceId, setActiveWorkspaceId] = useAtom(activeWorkspaceIdAtom);
  const [workspaces] = useAtom(workspacesAtom);
  const [notifications, setNotifications] = useAtom(notificationsAtom);
  const [unreadNotificationCount, setUnreadNotificationCount] = useAtom(unreadNotificationCountAtom);
  const [pendingNotificationCount, setPendingNotificationCount] = useAtom(pendingNotificationCountAtom);
  const [showScratchPad, setShowScratchPad] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; items: ContextMenuItemDef[] } | null>(null);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ChatSearchResultResponse[]>([]);
  const [renameInput, setRenameInput] = useState<{ id: number; value: string; scope: RenameScope } | null>(null);
  const [companyPrompts, setCompanyPrompts] = useState<CompanyPromptResponse[]>([]);
  const [userPrompts, setUserPrompts] = useState<UserPromptRecord[]>([]);
  const [promptSelections, setPromptSelections] = useState<Record<string, string>>(readPromptSelectionMap);
  const [pendingPromptId, setPendingPromptId] = useState<string | null>(null);
  const [utilityPanel, setUtilityPanel] = useState<UtilityPanel | null>(null);
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(null);
  const [sideBySideOpen, setSideBySideOpen] = useState(false);
  const [activeSplitPane, setActiveSplitPane] = useState<SplitPaneKey>("left");
  const [splitPaneSessionIds, setSplitPaneSessionIds] = useState<Record<SplitPaneKey, number | null>>({ left: null, right: null });
  const [pendingAttachments, setPendingAttachments] = useState<PendingSessionAttachment[]>([]);
  const [isUploadingAttachments, setIsUploadingAttachments] = useState(false);
  const [sendingSessions, setSendingSessions] = useState<Record<number, boolean>>({});
  const [attachmentDragTargetPane, setAttachmentDragTargetPane] = useState<SplitPaneKey | null>(null);
  const [deleteConfirmSessionId, setDeleteConfirmSessionId] = useState<number | null>(null);
  const [deleteMessageTarget, setDeleteMessageTarget] = useState<ChatMessage | null>(null);
  const [deleteLastMessageTarget, setDeleteLastMessageTarget] = useState<ChatMessage | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);
  const [deletedMessageUndo, setDeletedMessageUndo] = useState<{ sessionId: number; messageIds: number[] } | null>(null);
  const [regenerateTarget, setRegenerateTarget] = useState<ChatMessage | null>(null);
  const [regenerateModelKey, setRegenerateModelKey] = useState<string | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editingDraft, setEditingDraft] = useState("");
  const [feedbackTarget, setFeedbackTarget] = useState<ChatMessage | null>(null);
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [messageActionBusyId, setMessageActionBusyId] = useState<number | null>(null);
  const [moveSessionId, setMoveSessionId] = useState<number | null>(null);
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [skillPanelVisible, setSkillPanelVisible] = useState(false);
  const [skillPanelIndex, setSkillPanelIndex] = useState(0);
  const [slashCommand, setSlashCommand] = useState<SlashCommandMatch | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillResponse | null>(null);
  const [selectedBuiltinCommand, setSelectedBuiltinCommand] = useState<BuiltinSlashCommand | null>(null);
  const [llmProviders, setLlmProviders] = useState<LLMProviderStatusResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelConfigError, setModelConfigError] = useState("");
  const [selectedModelKey, setSelectedModelKey] = useState<string | null>(null);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsInitialAdminTab, setSettingsInitialAdminTab] = useState<SettingsAdminTab | null>(null);
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false);
  const [notificationView, setNotificationView] = useState<NotificationView>("all");
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationToast, setNotificationToast] = useState<NotificationResponse | null>(null);
  const [clientVersion, setClientVersion] = useState(FALLBACK_CLIENT_VERSION);
  const [availableUpdate, setAvailableUpdate] = useState<ClientUpdateInfo | null>(null);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [updateStep, setUpdateStep] = useState<ClientUpdateStep>("available");
  const [updateProgress, setUpdateProgress] = useState<UpdateDownloadProgress | null>(null);
  const [downloadedUpdatePath, setDownloadedUpdatePath] = useState("");
  const [updateError, setUpdateError] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(readSidebarWidth);
  const [sidebarResizing, setSidebarResizing] = useState(false);
  const [workspacePanelWidth, setWorkspacePanelWidth] = useState(readWorkspacePanelWidth);
  const [workspacePanelResizing, setWorkspacePanelResizing] = useState(false);
  const [auxiliaryPanelWidth, setAuxiliaryPanelWidth] = useState(readAuxiliaryPanelWidth);
  const [auxiliaryPanelResizing, setAuxiliaryPanelResizing] = useState(false);
  const workspacePanelWidthBeforePreviewRef = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const titleInputRef = useRef<HTMLInputElement | null>(null);
  const sidebarRenameInputRef = useRef<HTMLInputElement | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);
  const workspacePanelRef = useRef<HTMLElement | null>(null);
  const auxiliaryPanelRef = useRef<HTMLElement | null>(null);
  const composerRef = useRef<HTMLDivElement | null>(null);
  const modelSelectRef = useRef<HTMLDivElement | null>(null);
  const notificationPanelRef = useRef<HTMLDivElement | null>(null);
  const notificationButtonRef = useRef<HTMLButtonElement | null>(null);
  const pendingAttachmentPreviewsRef = useRef<Set<string>>(new Set());
  const copyResetTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const undoDeleteTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const notificationStartedAtRef = useRef(new Date());
  const notificationInitializedRef = useRef(false);
  const notificationToastIdsRef = useRef<Set<number>>(new Set());
  const notificationToastTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const updateCheckStartedRef = useRef(false);
  const previousWorkspaceIdRef = useRef<number | null | undefined>(undefined);
  const sendAbortControllersRef = useRef<Map<number, AbortController>>(new Map());
  const typingTimersRef = useRef<Map<number, ReturnType<typeof window.setInterval>>>(new Map());

  const apiOptions = useMemo(
    () => createApiOptions(serverUrl, token, clearAuth),
    [clearAuth, serverUrl, token],
  );
  function toggleWebSearch() {
    setWebSearchEnabled((current) => {
      const next = !current;
      writeWebSearchPreference(next);
      return next;
    });
  }

  const activeSessionIsSending = activeSessionId ? Boolean(sendingSessions[activeSessionId]) : false;
  const activeWorkspace = workspaces.find((item) => item.id === activeWorkspaceId);
  const promptOptions = useMemo<PromptOption[]>(() => [
    PROJECT_R_BUILTIN_PROMPT,
    ...companyPrompts.map((prompt) => ({
      id: prompt.id,
      source: "company" as const,
      name: prompt.name,
      description: prompt.description,
      content: prompt.content,
    })),
    ...userPrompts.map((prompt) => ({
      id: prompt.id,
      source: "user" as const,
      name: prompt.name,
      description: "仅本机可用",
      content: prompt.content,
    })),
  ], [companyPrompts, userPrompts]);
  const defaultPromptId = makePromptId(PROJECT_R_BUILTIN_PROMPT.source, PROJECT_R_BUILTIN_PROMPT.id);
  const selectedPromptId = activeSessionId
    ? promptSelections[String(activeSessionId)] ?? defaultPromptId
    : pendingPromptId ?? defaultPromptId;
  const matchedPrompt = promptOptions.find((prompt) => getPromptOptionId(prompt) === selectedPromptId);
  const selectedPrompt = matchedPrompt ?? PROJECT_R_BUILTIN_PROMPT;
  const selectedPromptIsDefault = !matchedPrompt || selectedPromptId === defaultPromptId;
  const modelOptions = useMemo(() => {
    return llmProviders
      .filter((provider) => provider.configured)
      .map(toModelOption)
      .sort((a, b) => Number(b.isDefault) - Number(a.isDefault) || a.label.localeCompare(b.label, "zh-CN"));
  }, [llmProviders]);
  const selectedModelOption = modelOptions.find((option) => option.key === selectedModelKey) ?? modelOptions.find((option) => option.isDefault) ?? modelOptions[0] ?? null;
  const regenerateModelOption = modelOptions.find((option) => option.key === regenerateModelKey) ?? selectedModelOption;
  const sessionGroups = useMemo(() => {
    const pinned = sessions.filter((item) => item.is_pinned);
    const recent = sessions.filter((item) => !item.is_pinned);
    const timeGroups = groupSessionsByTime(recent);
    return [
      ...(pinned.length ? [{ key: "pinned", label: null as string | null, items: pinned }] : []),
      ...timeGroups,
    ];
  }, [sessions]);

  const skillQuery = slashCommand?.query ?? "";
  const slashCandidates = useMemo<SkillSlashCandidate[]>(() => {
    const builtinCandidates: SkillSlashCandidate[] = BUILTIN_SLASH_COMMANDS
      .map((command) => ({ kind: "command" as const, command, score: scoreBuiltinSlashCommand(command, skillQuery) }))
      .filter((item) => !skillQuery || item.score > 0);
    const skillCandidates: SkillSlashCandidate[] = skills
      .map((skill) => ({ kind: "skill" as const, skill, score: scoreSkill(skill, skillQuery) }))
      .filter((item) => !skillQuery || item.score > 0);
    return [...builtinCandidates, ...skillCandidates]
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        if (a.kind !== b.kind) return a.kind === "command" ? -1 : 1;
        const aName = a.kind === "command" ? a.command.displayName : a.skill.display_name;
        const bName = b.kind === "command" ? b.command.displayName : b.skill.display_name;
        return aName.localeCompare(bName, "zh-CN");
      })
      .slice(0, 8);
  }, [skills, skillQuery]);

  function syncSlashCommand(value: string, caret: number) {
    const command = findSlashCommand(value, caret);
    setSlashCommand(command);
    setSkillPanelVisible(Boolean(command));
    if (!command) setSkillPanelIndex(0);
  }

  function clearSelectedSkillIfMissing(_value: string) {
    // Skill 选择是本次发送的上下文状态，不再依赖输入框里的触发词。
  }

  function insertSkill(skill: SkillResponse) {
    const target = slashCommand ?? findSlashCommand(draft, textareaRef.current?.selectionStart ?? draft.length);
    if (!target) return;
    const before = draft.slice(0, target.start).replace(/[ \t]+$/, "");
    const after = draft.slice(target.end).replace(/^[ \t]+/, "");
    const spacer = before && after ? " " : "";
    const nextDraft = `${before}${spacer}${after}`;
    const nextCaret = before.length + spacer.length;
    setDraft(nextDraft);
    setSelectedSkill(skill);
    setSelectedBuiltinCommand(null);
    setSlashCommand(null);
    setSkillPanelVisible(false);
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
    });
    if (mode === "chat" && skill.outputs.length > 0) {
      setMode("agent");
    }
  }

  function insertBuiltinSlashCommand(command: BuiltinSlashCommand) {
    const target = slashCommand ?? findSlashCommand(draft, textareaRef.current?.selectionStart ?? draft.length);
    if (!target) return;
    const before = draft.slice(0, target.start).replace(/[ \t]+$/, "");
    const after = draft.slice(target.end).replace(/^[ \t]+/, "");
    const spacer = before && after ? " " : "";
    const nextDraft = `${before}${spacer}${after}`;
    const nextCaret = before.length + spacer.length;
    setDraft(nextDraft);
    setSelectedSkill(null);
    setSelectedBuiltinCommand(command);
    setSlashCommand(null);
    setSkillPanelVisible(false);
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
    });
  }

  function insertSlashCandidate(candidate: SkillSlashCandidate) {
    if (candidate.kind === "command") {
      insertBuiltinSlashCommand(candidate.command);
      return;
    }
    insertSkill(candidate.skill);
  }

  async function loadNotificationList(view = notificationView) {
    setNotificationsLoading(true);
    try {
      const response = await listNotifications(apiOptions, view);
      setNotifications(response.items);
      setUnreadNotificationCount(response.unread_count);
      setPendingNotificationCount(response.pending_count);
    } catch {
      setNotifications([]);
    } finally {
      setNotificationsLoading(false);
    }
  }

  function showNotificationToast(notification: NotificationResponse) {
    if (!shouldToastNotification(notification) || notificationToastIdsRef.current.has(notification.id)) return;
    notificationToastIdsRef.current.add(notification.id);
    setNotificationToast(notification);
    if (notificationToastTimerRef.current) {
      window.clearTimeout(notificationToastTimerRef.current);
    }
    notificationToastTimerRef.current = window.setTimeout(() => {
      setNotificationToast(null);
    }, 5000);
  }

  async function refreshNotificationCounts({ allowToast = false } = {}) {
    try {
      const previousUnread = unreadNotificationCount;
      const counts = await getNotificationCounts(apiOptions);
      setUnreadNotificationCount(counts.unread_count);
      setPendingNotificationCount(counts.pending_count);
      if (
        allowToast &&
        notificationInitializedRef.current &&
        counts.unread_count > previousUnread
      ) {
        const response = await listNotifications(apiOptions, "unread", 5);
        const startedAt = notificationStartedAtRef.current.getTime();
        const toastTarget = response.items.find((item) => {
          const createdAt = parseApiDate(item.created_at).getTime();
          return createdAt >= startedAt && shouldToastNotification(item);
        });
        if (toastTarget) showNotificationToast(toastTarget);
      }
      notificationInitializedRef.current = true;
    } catch {
      // Notification polling must not interrupt chat usage.
    }
  }

  async function markNotificationReadAndRefresh(notification: NotificationResponse) {
    if (!notification.is_read) {
      await markNotificationRead(apiOptions, notification.id);
    }
    await refreshNotificationCounts();
    if (notificationPanelOpen) {
      await loadNotificationList(notificationView);
    }
  }

  async function handleMarkAllNotificationsRead() {
    try {
      await markAllNotificationsRead(apiOptions);
      await refreshNotificationCounts();
      await loadNotificationList(notificationView);
    } catch {
      setError("无法将通知全部标记为已读。");
    }
  }

  async function handleNotificationAction(notification: NotificationResponse) {
    try {
      await markNotificationReadAndRefresh(notification);
      const payload = notification.action_payload ?? {};
      if (notification.action_kind === "open_workspace") {
        const workspaceId = numericPayloadValue(payload, "workspace_id");
        if (workspaceId) {
          setActiveWorkspaceId(workspaceId);
          setUtilityPanel("workspace");
          setNotificationPanelOpen(false);
        }
        return;
      }
      if (notification.action_kind === "open_session") {
        const sessionId = numericPayloadValue(payload, "session_id");
        const targetSession = sessionId ? sessions.find((session) => session.id === sessionId) : null;
        if (targetSession) {
          selectSession(targetSession);
          setNotificationPanelOpen(false);
        }
        return;
      }
      if (notification.action_kind === "open_admin_review") {
        setSettingsInitialAdminTab("reviews");
        setShowSettings(true);
        setNotificationPanelOpen(false);
        return;
      }
      if (notification.action_kind === "open_settings") {
        const tab = stringPayloadValue(payload, "tab");
        setSettingsInitialAdminTab(
          tab && ["overview", "users", "reviews", "gbrain", "templates", "updates", "audit"].includes(tab)
            ? (tab as SettingsAdminTab)
            : "overview",
        );
        setShowSettings(true);
        setNotificationPanelOpen(false);
        return;
      }
      if (notification.action_kind === "download_file" || notification.action_kind === "open_skill_run") {
        const fileId = stringPayloadValue(payload, "file_id");
        const downloadUrl = stringPayloadValue(payload, "download_url") ?? (fileId ? `/documents/${fileId}/download` : null);
        if (fileId && downloadUrl) {
          await downloadGeneratedFile(serverUrl, token, {
            id: fileId,
            filename: stringPayloadValue(payload, "filename") ?? "Project_R文件",
            mime_type: "application/octet-stream",
            download_url: downloadUrl,
          });
          setNotificationPanelOpen(false);
        }
      }
    } catch {
      setError("通知操作失败，请稍后重试。");
    }
  }

  async function handleNotificationActionStatus(notification: NotificationResponse, status: "done" | "dismissed") {
    try {
      await updateNotificationActionStatus(apiOptions, notification.id, status);
      await loadNotificationList(notificationView);
      await refreshNotificationCounts();
    } catch {
      setError(status === "done" ? "无法完成该待办通知。" : "无法忽略该待办通知。");
    }
  }

  async function checkForClientUpdate() {
    try {
      const currentVersion = await resolveCurrentClientVersion();
      const platform = window.projectR?.platform ?? "win32";
      setClientVersion(currentVersion);
      const response = await getLatestClientUpdate(
        { baseUrl: serverUrl, token: null, onUnauthorized: undefined },
        currentVersion,
        platform,
      );
      if (response.latest && compareClientVersions(currentVersion, response.latest.version) >= 0) {
        setAvailableUpdate(null);
        setUpdateDialogOpen(false);
        setUpdateStep("available");
        setUpdateProgress(null);
        setDownloadedUpdatePath("");
        setUpdateError("");
        return;
      }
      if (response.update_available && response.latest) {
        setAvailableUpdate(response.latest);
        setUpdateStep("available");
        setUpdateProgress(null);
        setDownloadedUpdatePath("");
        setUpdateError("");
        setUpdateDialogOpen(true);
      }
    } catch {
      // Update checks are opportunistic and must not block login or chat usage.
    }
  }

  async function startClientUpdateDownload() {
    if (!availableUpdate) return;
    if (!window.projectR?.updates?.download || !window.projectR?.updates?.install) {
      setUpdateStep("failed");
      setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      return;
    }
    setUpdateStep("downloading");
    setUpdateError("");
    setDownloadedUpdatePath("");
    setUpdateProgress({
      version: availableUpdate.version,
      status: "downloading",
      receivedBytes: 0,
      totalBytes: availableUpdate.size_bytes,
      percent: 0,
      bytesPerSecond: 0,
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    const result = await window.projectR.updates.download({
      baseUrl: serverUrl,
      token,
      version: availableUpdate.version,
      filename: availableUpdate.filename,
      downloadUrl: availableUpdate.download_url,
      sha256: availableUpdate.sha256,
      sizeBytes: availableUpdate.size_bytes,
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    if (!result.ok || !result.filePath) {
      setUpdateStep("failed");
      setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      return;
    }
    setDownloadedUpdatePath(result.filePath);
    setUpdateStep("installing");
    setUpdateProgress({
      version: availableUpdate.version,
      status: "installing",
      receivedBytes: availableUpdate.size_bytes,
      totalBytes: availableUpdate.size_bytes,
      percent: 100,
      bytesPerSecond: 0,
      filePath: result.filePath,
      message: "正在静默安装更新，完成后会自动重启应用...",
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    const installResult = await window.projectR.updates.install({
      filePath: result.filePath,
      version: availableUpdate.version,
      dryRun: UPDATE_DOWNLOAD_DRY_RUN,
    });
    if (!installResult.ok) {
      setUpdateStep("failed");
      setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      return;
    }
    if (installResult.dryRun) {
      setUpdateDialogOpen(false);
    }
  }

  function handleSidebarResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    setSidebarResizing(true);
  }

  function handleWorkspacePanelResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    setWorkspacePanelResizing(true);
  }

  function handleAuxiliaryPanelResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    setAuxiliaryPanelResizing(true);
  }

  function handleWorkspaceFilePreviewOpen() {
    if (workspacePanelWidthBeforePreviewRef.current === null) {
      workspacePanelWidthBeforePreviewRef.current = workspacePanelWidth;
    }
    const previewPanelWidth = clampWorkspacePanelWidth(WORKSPACE_PANEL_PREVIEW_WIDTH);
    setWorkspacePanelWidth((width) => Math.max(width, previewPanelWidth));
  }

  function handleWorkspaceFilePreviewClose() {
    const savedWidth = workspacePanelWidthBeforePreviewRef.current;
    workspacePanelWidthBeforePreviewRef.current = null;
    if (savedWidth !== null) {
      setWorkspacePanelWidth(clampWorkspacePanelWidth(savedWidth));
    } else {
      setWorkspacePanelWidth(clampWorkspacePanelWidth(WORKSPACE_PANEL_DEFAULT_WIDTH));
    }
  }

  useEffect(() => {
    writeSidebarWidth(sidebarWidth);
  }, [sidebarWidth]);

  useEffect(() => {
    writeWorkspacePanelWidth(workspacePanelWidth);
  }, [workspacePanelWidth]);

  useEffect(() => {
    writeAuxiliaryPanelWidth(auxiliaryPanelWidth);
  }, [auxiliaryPanelWidth]);

  useEffect(() => {
    function handleWindowResize() {
      setSidebarWidth((width) => clampSidebarWidth(width));
      setWorkspacePanelWidth((width) => clampWorkspacePanelWidth(width));
      setAuxiliaryPanelWidth((width) => clampAuxiliaryPanelWidth(width));
    }
    window.addEventListener("resize", handleWindowResize);
    return () => window.removeEventListener("resize", handleWindowResize);
  }, []);

  useEffect(() => {
    if (!sidebarResizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const left = sidebarRef.current?.getBoundingClientRect().left ?? 0;
      setSidebarWidth(clampSidebarWidth(event.clientX - left));
    }

    function handleMouseUp() {
      setSidebarResizing(false);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [sidebarResizing]);

  useEffect(() => {
    if (!workspacePanelResizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const right = workspacePanelRef.current?.getBoundingClientRect().right ?? window.innerWidth;
      setWorkspacePanelWidth(clampWorkspacePanelWidth(right - event.clientX));
    }

    function handleMouseUp() {
      setWorkspacePanelResizing(false);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [workspacePanelResizing]);

  useEffect(() => {
    if (!auxiliaryPanelResizing) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const right = auxiliaryPanelRef.current?.getBoundingClientRect().right ?? window.innerWidth;
      setAuxiliaryPanelWidth(clampAuxiliaryPanelWidth(right - event.clientX));
    }

    function handleMouseUp() {
      setAuxiliaryPanelResizing(false);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [auxiliaryPanelResizing]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [scrollRef.current, activeSplitPane, splitPaneSessionIds]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Follow bottom only if user was already near bottom BEFORE this update
    if (isNearBottomRef.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    }
  }, [activeMessages]);

  useEffect(() => {
    return () => {
      if (copyResetTimerRef.current) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      if (undoDeleteTimerRef.current) {
        window.clearTimeout(undoDeleteTimerRef.current);
      }
      if (notificationToastTimerRef.current) {
        window.clearTimeout(notificationToastTimerRef.current);
      }
      revokeAllAttachmentPreviews();
    };
  }, []);

  useEffect(() => {
    setSkillPanelIndex(0);
  }, [skillQuery]);

  useEffect(() => {
    setSkillPanelIndex((index) => {
      if (slashCandidates.length === 0) return 0;
      return Math.min(index, slashCandidates.length - 1);
    });
  }, [slashCandidates.length]);

  useEffect(() => {
    function handlePointerDown(event: globalThis.MouseEvent) {
      const target = event.target;
      const insideComposer = target instanceof Node && Boolean(composerRef.current?.contains(target));
      const insideModelSelect = target instanceof Node && Boolean(modelSelectRef.current?.contains(target));
      const insideNotificationPanel = target instanceof Node && Boolean(notificationPanelRef.current?.contains(target));
      const insideNotificationButton = target instanceof Node && Boolean(notificationButtonRef.current?.contains(target));
      if (modelMenuOpen && !insideModelSelect) {
        setModelMenuOpen(false);
      }
      if (skillPanelVisible && !insideComposer) {
        setSkillPanelVisible(false);
        setSlashCommand(null);
      }
      if (notificationPanelOpen && !insideNotificationPanel && !insideNotificationButton) {
        setNotificationPanelOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [modelMenuOpen, notificationPanelOpen, skillPanelVisible]);

  useEffect(() => {
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        setNotificationPanelOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (!token) return;
    void refreshNotificationCounts();
    const timer = window.setInterval(() => {
      void refreshNotificationCounts({ allowToast: true });
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [apiOptions, token, unreadNotificationCount]);

  useEffect(() => {
    if (!notificationPanelOpen || !token) return;
    void loadNotificationList(notificationView);
  }, [notificationPanelOpen, notificationView, token]);

  useEffect(() => {
    if (!window.projectR?.updates?.onProgress) return;
    return window.projectR.updates.onProgress((progress) => {
      setUpdateProgress(progress);
      if (progress.status === "downloading" || progress.status === "verifying") {
        setUpdateStep("downloading");
      }
      if (progress.status === "installing") {
        setUpdateStep("installing");
      }
      if (progress.status === "ready") {
        setDownloadedUpdatePath(progress.filePath ?? "");
        setUpdateStep("downloading");
      }
      if (progress.status === "error") {
        setUpdateStep("failed");
        setUpdateError("自动更新失败，请联系管理员获取最新版安装包。");
      }
    });
  }, []);

  useEffect(() => {
    const handleEscapeCancel = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape" || !activeSessionIsSending) return;
      event.preventDefault();
      handleCancelSend(activeSessionId);
    };
    window.addEventListener("keydown", handleEscapeCancel);
    return () => window.removeEventListener("keydown", handleEscapeCancel);
  }, [activeSessionId, activeSessionIsSending]);

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

  useEffect(() => {
    if (!token || updateCheckStartedRef.current) return;
    updateCheckStartedRef.current = true;
    void checkForClientUpdate();
  }, [serverUrl, token]);

  useEffect(() => {
    if (utilityPanel === "source" && sourcePreview?.sessionId != null && sourcePreview.sessionId !== activeSessionId) {
      setSourcePreview(null);
      setUtilityPanel(null);
    }
  }, [activeSessionId, sourcePreview?.sessionId, utilityPanel]);

  useEffect(() => {
    setPendingAttachments((current) => {
      const next = current.filter((attachment) => attachment.session_id === activeSessionId);
      if (next.length === current.length) return current;
      revokeAttachmentPreviews(current.filter((attachment) => attachment.session_id !== activeSessionId));
      return next;
    });
  }, [activeSessionId]);

  useEffect(() => {
    const previousWorkspaceId = previousWorkspaceIdRef.current;
    previousWorkspaceIdRef.current = activeWorkspaceId;
    if (previousWorkspaceId === undefined || previousWorkspaceId === activeWorkspaceId) return;
    setPendingAttachments((current) => {
      if (!current.length) return current;
      revokeAttachmentPreviews(current);
      return [];
    });
  }, [activeWorkspaceId]);

  useEffect(() => {
    setTabs((current) => {
      if (!current.some((tab) => tab.id === "scratch")) return current;
      return current.filter((tab) => tab.id !== "scratch");
    });
    if (activeTabId === "scratch") {
      setActiveTabId("");
      setActiveSessionId(null);
    }
  }, [activeTabId, setActiveSessionId, setActiveTabId, setTabs]);

  useEffect(() => {
    let mounted = true;
    setIsLoading(true);
    setError(null);
    if (!activeWorkspaceId) {
      setSessions([]);
      setActiveSessionId(null);
      setIsLoading(false);
      return;
    }
    listChatSessions(apiOptions, activeWorkspaceId)
      .then((loadedSessions) => {
        if (!mounted) return;
        setSessions(loadedSessions);
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

  useEffect(() => {
    let mounted = true;
    setModelsLoading(true);
    setModelConfigError("");
    getLLMHealth(apiOptions)
      .then((health) => {
        if (!mounted) return;
        setLlmProviders(health.providers);
      })
      .catch(() => {
        if (!mounted) return;
        setLlmProviders([]);
        setModelConfigError("无法读取模型配置");
      })
      .finally(() => {
        if (mounted) setModelsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  useEffect(() => {
    if (modelOptions.length === 0) {
      setSelectedModelKey(null);
      return;
    }
    if (selectedModelKey && modelOptions.some((option) => option.key === selectedModelKey)) return;
    setSelectedModelKey((modelOptions.find((option) => option.isDefault) ?? modelOptions[0]).key);
  }, [modelOptions, selectedModelKey]);

  useEffect(() => {
    let mounted = true;
    listCompanyPrompts(apiOptions)
      .then((items) => {
        if (mounted) setCompanyPrompts(items);
      })
      .catch(() => {
        if (mounted) setCompanyPrompts([]);
      });
    listSkills(apiOptions)
      .then((items) => {
        if (mounted) setSkills(items);
      })
      .catch(() => {
        if (mounted) setSkills([]);
      });
    window.projectR?.prompts?.listUser()
      .then((items) => {
        if (mounted) setUserPrompts(items);
      })
      .catch(() => {
        if (mounted) setUserPrompts([]);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  useEffect(() => {
    if (!activeSessionId || messagesBySession[activeSessionId]) return;
    let mounted = true;
    setIsLoading(true);
    setError(null);
    listChatMessages(apiOptions, activeSessionId)
      .then((response) => {
        if (!mounted) return;
        setMessagesBySession((current) => ({ ...current, [activeSessionId]: response.items }));
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
      if (openInNewTab || !activeTabId) return [...current, nextTab];
      if (!current.some((tab) => tab.id === activeTabId)) return [...current, nextTab];
      return current.map((tab) => tab.id === activeTabId ? nextTab : tab);
    });
    setActiveTabId(tabId);
  }

  async function handleArchiveRestored(session: ChatSessionResponse) {
    const workspaceId = session.workspace_id ?? activeWorkspaceId;
    if (!workspaceId) return;
    if (workspaceId !== activeWorkspaceId) {
      setActiveWorkspaceId(workspaceId);
    }
    try {
      const refreshedSessions = await listChatSessions(apiOptions, workspaceId);
      setSessions(refreshedSessions);
      const restoredSession = refreshedSessions.find((item) => item.id === session.id) ?? { ...session, is_archived: false };
      selectSession(restoredSession);
    } catch {
      if (workspaceId === activeWorkspaceId) {
        const restoredSession = { ...session, is_archived: false };
        setSessions((current) => current.some((item) => item.id === session.id) ? current : [restoredSession, ...current]);
        selectSession(restoredSession);
      }
    }
  }

  function storePromptSelection(sessionId: number, promptId: string) {
    setPromptSelections((current) => {
      const next = { ...current, [String(sessionId)]: promptId };
      localStorage.setItem(PROMPT_SELECTION_KEY, JSON.stringify(next));
      return next;
    });
  }

  function clearPromptSelection() {
    if (!activeSessionId) {
      setPendingPromptId(null);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    setPromptSelections((current) => {
      const next = { ...current };
      delete next[String(activeSessionId)];
      localStorage.setItem(PROMPT_SELECTION_KEY, JSON.stringify(next));
      return next;
    });
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function createSessionFromInput(
    content = "新对话",
    openInNewTab = true,
    promptIdForNewSession: string | null = null,
    paneForNewSession: SplitPaneKey = activeSplitPane,
  ) {
    const resolvedPromptId = promptIdForNewSession ?? (!activeSessionId ? pendingPromptId : null);
    const session = await createChatSession(apiOptions, makeSessionTitle(content), activeWorkspaceId);
    setSessions((current) => [session, ...current]);
    setMessagesBySession((current) => ({ ...current, [session.id]: [] }));
    if (resolvedPromptId) {
      if (resolvedPromptId !== defaultPromptId) {
        storePromptSelection(session.id, resolvedPromptId);
      }
      setPendingPromptId(null);
    }
    selectSession(session, openInNewTab);
    if (sideBySideOpen) {
      setSplitPaneSessionIds((current) => ({ ...current, [paneForNewSession]: session.id }));
    }
    return session;
  }

  async function handleCreateSession() {
    setError(null);
    if (!activeWorkspaceId) {
      setError("请先选择或创建一个项目。");
      return;
    }
    try {
      await createSessionFromInput();
    } catch (createError: unknown) {
      if (createError instanceof ApiError && createError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("新建会话失败，请确认后端连接正常。");
    }
  }

  function handleOpenScratch() {
    setShowScratchPad((current) => {
      const next = !current;
      if (next) {
        setUtilityPanel(null);
      }
      return next;
    });
  }

  async function handleDeleteSession(sessionId: number) {
    setError(null);
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

  async function handleCopyMessage(message: ChatMessage) {
    try {
      await copyText(message.content, true);
      setCopiedMessageId(message.id);
      if (copyResetTimerRef.current) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      copyResetTimerRef.current = window.setTimeout(() => {
        setCopiedMessageId(null);
        copyResetTimerRef.current = null;
      }, 1500);
    } catch {
      setError("复制失败：当前浏览器拒绝剪贴板权限。");
    }
  }

  function getMessageDeleteTargetIds(target: ChatMessage) {
    const sessionMessages = (messagesBySession[target.session_id] ?? [])
      .filter((message) => message.id > 0)
      .sort((a, b) => {
        const timeDiff = parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime();
        return timeDiff || a.id - b.id;
      });
    const targetIndex = sessionMessages.findIndex((message) => message.id === target.id);
    if (targetIndex < 0) return target.id > 0 ? [target.id] : [];
    if (target.role !== "user") return [target.id];

    const targetIds: number[] = [];
    for (let index = targetIndex; index < sessionMessages.length; index += 1) {
      const message = sessionMessages[index];
      if (index !== targetIndex && message.role === "user") break;
      targetIds.push(message.id);
    }
    return targetIds.length > 0 ? targetIds : [target.id];
  }

  function willDeleteEntireSession(target: ChatMessage) {
    if (target.id < 0) return false;
    const sessionMessages = (messagesBySession[target.session_id] ?? []).filter((message) => message.id > 0);
    if (sessionMessages.length === 0) return false;
    const deleteIds = new Set(getMessageDeleteTargetIds(target));
    return sessionMessages.every((message) => deleteIds.has(message.id));
  }

  function requestDeleteMessageContext(target: ChatMessage) {
    if (willDeleteEntireSession(target)) {
      setDeleteLastMessageTarget(target);
      return;
    }
    setDeleteMessageTarget(target);
  }

  async function handleDeleteMessageContext(target: ChatMessage) {
    if (target.id < 0) return;
    setError(null);
    try {
      const response = await deleteChatMessage(apiOptions, target.session_id, target.id);
      const excludedIds = new Set(response.excluded_message_ids);
      setMessagesBySession((current) => ({
        ...current,
        [target.session_id]: (current[target.session_id] ?? []).filter((message) => !excludedIds.has(message.id)),
      }));
      setDeletedMessageUndo({ sessionId: target.session_id, messageIds: response.excluded_message_ids });
      if (undoDeleteTimerRef.current) {
        window.clearTimeout(undoDeleteTimerRef.current);
      }
      undoDeleteTimerRef.current = window.setTimeout(() => {
        setDeletedMessageUndo(null);
        undoDeleteTimerRef.current = null;
      }, 8000);
      if (sourcePreview?.sessionId === target.session_id) {
        setSourcePreview(null);
        setUtilityPanel((value) => value === "source" ? null : value);
      }
    } catch (deleteError: unknown) {
      if (deleteError instanceof ApiError && deleteError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("删除消息失败，请稍后重试。");
    }
  }

  async function handleUndoDeleteMessages() {
    if (!deletedMessageUndo) return;
    const undo = deletedMessageUndo;
    setError(null);
    try {
      const response = await restoreDeletedChatMessages(apiOptions, undo.sessionId, undo.messageIds);
      setMessagesBySession((current) => {
        const merged = [...(current[undo.sessionId] ?? []), ...response.messages];
        const byId = new Map<number, ChatMessage>();
        for (const message of merged) {
          byId.set(message.id, message);
        }
        return {
          ...current,
          [undo.sessionId]: Array.from(byId.values()).sort((a, b) => {
            const timeDiff = parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime();
            return timeDiff || a.id - b.id;
          }),
        };
      });
      setDeletedMessageUndo(null);
      if (undoDeleteTimerRef.current) {
        window.clearTimeout(undoDeleteTimerRef.current);
        undoDeleteTimerRef.current = null;
      }
    } catch (restoreError: unknown) {
      if (restoreError instanceof ApiError && restoreError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("撤回删除失败，请刷新消息后确认。");
    }
  }

  function replaceMessageInSession(sessionId: number, currentMessage: ChatMessage, nextMessage: ChatMessage) {
    setMessagesBySession((current) => ({
      ...current,
      [sessionId]: (current[sessionId] ?? []).map((message) =>
        message.id === currentMessage.id ||
        (message.version_group_id && message.version_group_id === currentMessage.version_group_id)
          ? { ...nextMessage }
          : message,
      ),
    }));
  }

  function openRegenerateDialog(message: ChatMessage) {
    setRegenerateTarget(message);
    setRegenerateModelKey(selectedModelOption?.key ?? null);
  }

  async function handleRegenerateMessage(target: ChatMessage) {
    if (target.id < 0 || !regenerateModelOption) return;
    setError(null);
    setMessageActionBusyId(target.id);
    setRegenerateTarget(null);
    setMessagesBySession((current) => ({
      ...current,
      [target.session_id]: (current[target.session_id] ?? []).map((message) =>
        message.id === target.id ? { ...message, isRegenerating: true, isTyping: false } : message,
      ),
    }));
    try {
      const response = await regenerateChatMessage(apiOptions, target.session_id, target.id, {
        provider: regenerateModelOption.provider,
        modelProfile: regenerateModelOption.profile,
        systemPrompt: composeSystemPrompt(selectedPrompt.content, mode),
        thinking: thinkingEnabled,
        webSearch: webSearchEnabled,
        temperature: 0.9,
      });
      const excludedIds = new Set(response.excluded_message_ids);
      const typingMessage: ChatMessage = {
        ...response.assistant_message,
        content: "",
        isTyping: true,
        isRegenerating: false,
      };
      setMessagesBySession((current) => ({
        ...current,
        [target.session_id]: (current[target.session_id] ?? [])
          .filter((message) => !excludedIds.has(message.id))
          .map((message) => message.id === target.id ? typingMessage : message),
      }));
      typeAssistantReply(target.session_id, typingMessage, response.assistant_message.content);
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    } catch (regenerateError: unknown) {
      setMessagesBySession((current) => ({
        ...current,
        [target.session_id]: (current[target.session_id] ?? []).map((message) =>
          message.id === target.id ? { ...target, isRegenerating: false, isTyping: false } : message,
        ),
      }));
      if (regenerateError instanceof ApiError && regenerateError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(regenerateError instanceof ApiError ? regenerateError.message : "重新生成失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  function startEditingMessage(message: ChatMessage) {
    setEditingMessageId(message.id);
    setEditingDraft(message.content);
  }

  async function handleSubmitEditedMessage(message: ChatMessage) {
    const content = editingDraft.trim();
    if (!content || content === message.content || message.id < 0) {
      setEditingMessageId(null);
      setEditingDraft("");
      return;
    }
    setError(null);
    setMessageActionBusyId(message.id);
    try {
      const response = await editChatMessage(apiOptions, message.session_id, message.id, {
        content,
        provider: selectedModelOption?.provider ?? null,
        modelProfile: selectedModelOption?.profile ?? null,
        systemPrompt: composeSystemPrompt(selectedPrompt.content, mode),
        thinking: thinkingEnabled,
        webSearch: webSearchEnabled,
      });
      const excludedIds = new Set(response.excluded_message_ids);
      setMessagesBySession((current) => {
        const existing = current[message.session_id] ?? [];
        const next: ChatMessage[] = [];
        for (const item of existing) {
          if (excludedIds.has(item.id)) continue;
          if (item.id === message.id) {
            next.push(response.user_message, response.assistant_message);
          } else {
            next.push(item);
          }
        }
        return { ...current, [message.session_id]: next };
      });
      setEditingMessageId(null);
      setEditingDraft("");
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    } catch (editError: unknown) {
      if (editError instanceof ApiError && editError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(editError instanceof ApiError ? editError.message : "编辑消息失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  async function handleActivateVersion(message: ChatMessage, version: ChatMessageVersionResponse) {
    if (version.active_version || message.id < 0) return;
    setError(null);
    setMessageActionBusyId(message.id);
    try {
      const response = await activateChatMessageVersion(apiOptions, message.session_id, message.id, version.id);
      replaceMessageInSession(message.session_id, message, response.message);
    } catch (versionError: unknown) {
      if (versionError instanceof ApiError && versionError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(versionError instanceof ApiError ? versionError.message : "切换消息版本失败。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  function openFeedbackDialog(message: ChatMessage) {
    setFeedbackTarget(message);
    setFeedbackRating(message.feedback_rating ?? 0);
    setFeedbackComment(message.feedback_comment ?? "");
  }

  async function handleSubmitFeedback() {
    if (!feedbackTarget || feedbackRating < 1) return;
    setError(null);
    setMessageActionBusyId(feedbackTarget.id);
    try {
      const response = await submitMessageFeedback(apiOptions, feedbackTarget.session_id, feedbackTarget.id, {
        rating: feedbackRating,
        comment: feedbackComment,
      });
      setMessagesBySession((current) => ({
        ...current,
        [feedbackTarget.session_id]: (current[feedbackTarget.session_id] ?? []).map((message) =>
          message.id === feedbackTarget.id
            ? { ...message, feedback_rating: response.rating, feedback_comment: response.comment }
            : message,
        ),
      }));
      setFeedbackTarget(null);
      setFeedbackRating(0);
      setFeedbackComment("");
    } catch (feedbackError: unknown) {
      if (feedbackError instanceof ApiError && feedbackError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(feedbackError instanceof ApiError ? feedbackError.message : "保存评分失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  async function handleSubmitGBrainThinkReview(message: ChatMessage) {
    if (message.id < 0) return;
    setError(null);
    setActionNotice("");
    setMessageActionBusyId(message.id);
    try {
      const response = await submitGBrainThinkReview(apiOptions, message.session_id, message.id, {});
      setActionNotice(
        response.created
          ? `已提交 GBrain 缺口/冲突审核 #${response.knowledge_review_id}。`
          : `已更新 GBrain 缺口/冲突审核 #${response.knowledge_review_id}。`,
      );
    } catch (reviewError: unknown) {
      if (reviewError instanceof ApiError && reviewError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(reviewError instanceof ApiError ? reviewError.message : "提交 GBrain 缺口/冲突审核失败。");
    } finally {
      setMessageActionBusyId(null);
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
          if (nextTab.workspaceId && nextTab.workspaceId !== activeWorkspaceId) {
            setActiveWorkspaceId(nextTab.workspaceId);
          }
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
      { type: "item", label: "删除", destructive: true, action: () => setDeleteConfirmSessionId(session.id) },
    );
    setContextMenu({ x: event.clientX, y: event.clientY, items });
  }

  function handleLogout() {
    clearAuth();
    window.location.hash = "#/login";
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

  function setSessionSending(sessionId: number, value: boolean) {
    setSendingSessions((current) => {
      const next = { ...current };
      if (value) next[sessionId] = true;
      else delete next[sessionId];
      return next;
    });
  }

  function isAbortError(value: unknown) {
    return value instanceof DOMException && value.name === "AbortError";
  }

  function handleCancelSend(sessionId: number | null | undefined) {
    if (!sessionId) return;
    sendAbortControllersRef.current.get(sessionId)?.abort();
    sendAbortControllersRef.current.delete(sessionId);
    const typingTimer = typingTimersRef.current.get(sessionId);
    if (typingTimer) {
      window.clearInterval(typingTimer);
      typingTimersRef.current.delete(sessionId);
      setMessagesBySession((current) => ({
        ...current,
        [sessionId]: (current[sessionId] ?? []).map((message) => message.isTyping ? { ...message, isTyping: false } : message),
      }));
    }
    setSessionSending(sessionId, false);
  }

  async function handleSend() {
    const content = draft.trim();
    if ((!content && !pendingAttachments.length) || activeSessionIsSending) return;
    const forceKnowledgeQuery = selectedBuiltinCommand?.name === "query";
    const startedFromWorkspaceHome = !activeSessionId;
    setError(null);
    let requestSessionId: number | null = null;
    let localUserMessageId: number | null = null;
    let uploadingForSend = false;

    try {
      const sessionTitleSeed = content || pendingAttachments[0]?.original_name || "附件提问";
      const session = activeSessionId
        ? sessions.find((item) => item.id === activeSessionId) ?? await createSessionFromInput(sessionTitleSeed)
        : await createSessionFromInput(sessionTitleSeed, true, selectedPromptId);
      const sessionId = session.id;
      if (sendingSessions[sessionId]) return;
      requestSessionId = sessionId;
      const attachmentsForSend = pendingAttachments.filter((attachment) => attachment.session_id === null || attachment.session_id === sessionId);
      if (!content && !attachmentsForSend.length) {
        throw new Error("请先输入消息或添加当前会话附件。");
      }
      const unauthorizedLocalAttachments = attachmentsForSend.filter(
        (attachment) => isLocalPrivatePendingAttachment(attachment) && attachment.authorization_status !== "authorized",
      );
      if (unauthorizedLocalAttachments.length) {
        throw new Error("请先确认本机选择文件的本次发送授权。");
      }
      const audioVideoAttachments = attachmentsForSend.filter(isAudioVideoAttachment);
      const canHandleAudioVideo =
        selectedSkill?.name === "audio-transcription" || (audioVideoAttachments.length > 0 && isAudioTranscriptionRequest(content));
      if (audioVideoAttachments.length > 0 && !canHandleAudioVideo) {
        throw new Error("当前版本暂未接入视频/音频附件理解，请先改用图片或可提取文本的附件。");
      }
      if (attachmentsForSend.some((attachment) => attachment.kind === "image") && !selectedModelOption?.supportsVision) {
        throw new Error("当前模型不支持图片理解，请切换到 MiMo V2.5 或 MiMo V2.5 Pro 后再发送。");
      }
      uploadingForSend = attachmentsForSend.some((attachment) => !isUploadedPendingAttachment(attachment));
      if (uploadingForSend) setIsUploadingAttachments(true);
      const sentAttachments: PendingSessionAttachment[] = [];
      for (const attachment of attachmentsForSend) {
        sentAttachments.push(await uploadPendingAttachmentForSend(attachment, sessionId));
      }
      if (uploadingForSend) {
        setIsUploadingAttachments(false);
        uploadingForSend = false;
      }
      const attachmentIds = sentAttachments.map((attachment) => String(attachment.id));
      setDraft("");
      setSelectedSkill(null);
      setSelectedBuiltinCommand(null);
      setSlashCommand(null);
      setSkillPanelVisible(false);
      const localUserMessage = makeLocalMessage(sessionId, "user", content, {
        isOptimistic: true,
        attachments: sentAttachments.map((attachment) => ({ ...attachment, session_id: sessionId, message_id: attachment.message_id ?? null })),
      });
      localUserMessageId = localUserMessage.id;
      setMessagesBySession((current) => ({
        ...current,
        [sessionId]: [...(current[sessionId] ?? []), localUserMessage],
      }));
      const abortController = new AbortController();
      sendAbortControllersRef.current.set(sessionId, abortController);
      setSessionSending(sessionId, true);

      if (session.title === "新对话") {
        const title = makeSessionTitle(content || sentAttachments[0]?.original_name || "附件提问");
        updateChatSession(apiOptions, sessionId, { title })
          .then((updated) => {
            setSessions((current) => current.map((item) => item.id === sessionId ? updated : item));
            setTabs((current) => current.map((tab) => tab.sessionId === sessionId ? { ...tab, title } : tab));
          })
          .catch(() => {});
      }

      const response = await sendChatMessage(
        apiOptions,
        sessionId,
        content,
        composeSystemPrompt(selectedPrompt.content, mode),
        attachmentIds,
        selectedModelOption?.provider ?? null,
        selectedModelOption?.profile ?? null,
        selectedSkill?.name ?? (audioVideoAttachments.length > 0 && isAudioTranscriptionRequest(content) ? "audio-transcription" : null),
        selectedPromptId,
        forceKnowledgeQuery,
        thinkingEnabled,
        webSearchEnabled,
        abortController.signal,
      );
      if (
        startedFromWorkspaceHome &&
        (response.skill_run || response.generated_file || response.intent === "skill_trigger" || response.intent === "document_generation")
      ) {
        setMode("agent");
      }
      setPendingAttachments((current) =>
        current.filter((attachment) => !attachmentsForSend.some((sent) => pendingAttachmentKey(sent) === pendingAttachmentKey(attachment))),
      );
      revokeAttachmentPreviews(attachmentsForSend);
      setSelectedSkill(null);
      const agentRequest = content || sentAttachments.map((attachment) => attachment.original_name).join(" ");
      const agentSuggestion = shouldSuggestAgentMode(agentRequest, response, mode);
      const assistantMessage = makeLocalMessage(sessionId, "assistant", "", {
        id: response.assistant_message_id,
        provider: response.provider,
        model: response.model,
        token_input: response.usage.input_tokens ?? null,
        token_output: response.usage.output_tokens ?? null,
        token_total:
          typeof response.usage.input_tokens === "number" &&
          typeof response.usage.output_tokens === "number"
            ? response.usage.input_tokens + response.usage.output_tokens
            : null,
        rag_used: Boolean(response.sources?.length),
        sources: response.sources ?? [],
        generated_file: response.generated_file ?? null,
        skill_run: response.skill_run ?? null,
        agent_run: response.agent_run ?? null,
        context_trace: response.context_trace ?? null,
        agent_suggestion: agentSuggestion ? { reason: agentSuggestion, request: agentRequest } : null,
        isTyping: true,
      });
      const serverUserAttachments = (response.user_attachments ?? sentAttachments.map((attachment) => ({ ...attachment, session_id: sessionId, message_id: response.user_message_id })))
        .map((attachment) => {
          const localAttachment = sentAttachments.find((item) => item.id === attachment.id);
          return localAttachment
            ? {
                ...attachment,
                source_scope: localAttachment.source_scope,
                source_label: localAttachment.source_label,
                authorization_status: localAttachment.authorization_status,
              }
            : attachment;
        });
      setMessagesBySession((current) => ({
        ...current,
        [sessionId]: [
          ...(current[sessionId] ?? []).map((message) =>
            message.id === localUserMessage.id
              ? { ...message, id: response.user_message_id, isOptimistic: false, attachments: serverUserAttachments }
              : message,
          ),
          assistantMessage,
        ],
      }));
      typeAssistantReply(sessionId, assistantMessage, response.reply);
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    } catch (sendError: unknown) {
      if (isAbortError(sendError)) {
        if (requestSessionId != null && localUserMessageId != null) {
          const abortedSessionId = requestSessionId;
          const abortedLocalMessageId = localUserMessageId;
          setMessagesBySession((current) => ({
            ...current,
            [abortedSessionId]: (current[abortedSessionId] ?? []).filter((message) => message.id !== abortedLocalMessageId),
          }));
        }
        return;
      }
      if (sendError instanceof ApiError && sendError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(sendError instanceof Error ? sendError.message : "消息发送失败，请稍后重试。");
    } finally {
      if (requestSessionId != null) {
        sendAbortControllersRef.current.delete(requestSessionId);
        setSessionSending(requestSessionId, false);
      }
      if (uploadingForSend) setIsUploadingAttachments(false);
    }
  }

  async function makeLocalPendingAttachment(
    file: File,
    source: AttachmentInputSource,
    privateWorkspaceRecord?: PrivateWorkspaceFilePayload,
  ): Promise<PendingSessionAttachment> {
    const kind = getAttachmentKind(file.name, file.type || "");
    const localId = privateWorkspaceRecord?.id ?? makeLocalAttachmentId();
    const sha256 = privateWorkspaceRecord?.sha256 ?? await hashFileSha256(file);
    const createdAt = new Date().toISOString();
    const isPrivateWorkspaceFile = Boolean(privateWorkspaceRecord);
    const authorizationStatus: AttachmentAuthorizationStatus =
      isPrivateWorkspaceFile && privateWorkspaceRecord?.lastAuthorizationStatus !== "authorized"
        ? "pending"
        : "authorized";
    let previewUrl: string | undefined;
    if (kind === "image") {
      previewUrl = URL.createObjectURL(file);
      pendingAttachmentPreviewsRef.current.add(previewUrl);
    }
    return {
      id: -Date.now(),
      local_id: localId,
      session_id: null,
      message_id: null,
      original_name: file.name,
      content_type: file.type || "application/octet-stream",
      size: file.size,
      created_at: createdAt,
      kind,
      previewUrl,
      file,
      sha256,
      relative_path: privateWorkspaceRecord?.relativePath ?? null,
      private_workspace_file_id: privateWorkspaceRecord?.id ?? null,
      preprocess: privateWorkspaceRecord?.preprocess ?? null,
      source_scope: isPrivateWorkspaceFile ? "local_private" : "session_upload",
      source_label: isPrivateWorkspaceFile ? "本机选择" : "会话临时上传",
      authorization_status: authorizationStatus,
      input_source: source,
    };
  }

  function makeUploadedPendingAttachment(
    attachment: SessionAttachmentResponse,
    file: File,
    source?: PendingSessionAttachment,
  ): PendingSessionAttachment {
    const kind = getAttachmentKind(attachment.original_name || file.name, attachment.content_type || file.type);
    return {
      ...attachment,
      local_id: source?.local_id ?? `server-${attachment.id}`,
      kind,
      previewUrl: source?.previewUrl,
      sha256: source?.sha256 ?? null,
      relative_path: source?.relative_path ?? null,
      private_workspace_file_id: source?.private_workspace_file_id ?? null,
      preprocess: source?.preprocess ?? null,
      source_scope: source?.private_workspace_file_id ? "local_private" : "session_upload",
      source_label: source?.source_label ?? (source?.private_workspace_file_id ? "本机选择" : "会话临时上传"),
      authorization_status: "uploaded",
      input_source: source?.input_source ?? "picker",
    };
  }

  function revokeAttachmentPreviews(attachments: PendingSessionAttachment[]) {
    for (const attachment of attachments) {
      if (!attachment.previewUrl) continue;
      URL.revokeObjectURL(attachment.previewUrl);
      pendingAttachmentPreviewsRef.current.delete(attachment.previewUrl);
    }
  }

  function revokeAllAttachmentPreviews() {
    for (const previewUrl of pendingAttachmentPreviewsRef.current) {
      URL.revokeObjectURL(previewUrl);
    }
    pendingAttachmentPreviewsRef.current.clear();
  }

  async function resolveAttachmentSession(target?: { sessionId?: number | null; pane?: SplitPaneKey }) {
    if (target?.pane) {
      setActiveSplitPane(target.pane);
    }
    if (target?.sessionId) {
      const targetSession = sessions.find((item) => item.id === target.sessionId);
      if (targetSession) {
        if (target.pane) activateConversationPane(target.pane, targetSession.id);
        return targetSession;
      }
    }
    if (activeSessionId) {
      const currentSession = sessions.find((item) => item.id === activeSessionId);
      if (currentSession) return currentSession;
    }
    return createSessionFromInput("附件会话", true, null, target?.pane ?? activeSplitPane);
  }

  async function handleSelectAttachmentFiles(
    inputFiles: FileList | File[] | null,
    source: AttachmentInputSource = "picker",
    target?: { sessionId?: number | null; pane?: SplitPaneKey },
  ) {
    const files = Array.from(inputFiles ?? []).filter((file) => file.size > 0);
    if (!files.length) return;
    setError(null);
    setIsUploadingAttachments(true);
    try {
      const tooLarge = files.find((file) => file.size > SESSION_ATTACHMENT_MAX_BYTES);
      if (tooLarge) {
        throw new Error(`${tooLarge.name} 超过 20MB，请改用当前工作区文件管理上传。`);
      }
      if (target?.pane) {
        setActiveSplitPane(target.pane);
        activateConversationPane(target.pane, target.sessionId ?? null);
      }
      const localAttachments = await Promise.all(files.map((file) => makeLocalPendingAttachment(file, source)));
      setPendingAttachments((current) => [...current, ...localAttachments]);
      if (source !== "picker") {
        window.requestAnimationFrame(() => textareaRef.current?.focus());
      }
    } catch (uploadError: unknown) {
      setError(uploadError instanceof Error ? uploadError.message : "附件上传失败，请稍后重试。");
    } finally {
      setIsUploadingAttachments(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleReferenceWorkspaceFile(item: WorkspaceFileItemResponse) {
    if (!activeWorkspaceId || item.type === "directory") return;
    setError(null);
    setIsUploadingAttachments(true);
    try {
      const blob = await fetchWorkspaceFileBlob(apiOptions, activeWorkspaceId, item.path);
      if (blob.size > SESSION_ATTACHMENT_MAX_BYTES) {
        throw new Error(`${item.name} 超过 20MB，暂不支持作为本轮引用附件发送。`);
      }
      const file = new File([blob], item.name, { type: blob.type || "application/octet-stream" });
      const attachment = await makeLocalPendingAttachment(file, "workspace_reference");
      setPendingAttachments((current) => [
        ...current,
        {
          ...attachment,
          relative_path: item.path,
          source_label: activeWorkspace?.workspace_kind === "customer" ? "CRM 文件引用" : "项目资料引用",
        },
      ]);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
    } catch (referenceError: unknown) {
      setError(referenceError instanceof Error ? referenceError.message : "引用文件失败，请稍后重试。");
    } finally {
      setIsUploadingAttachments(false);
    }
  }

  async function handleChoosePrivateWorkspaceFiles() {
    if (!window.projectR?.privateWorkspace) {
      setError("本机文件选择仅在桌面客户端可用；当前可用附件按钮作为会话临时上传处理。");
      return;
    }
    setError(null);
    setIsUploadingAttachments(true);
    try {
      const payloads = await window.projectR.privateWorkspace.chooseFiles();
      if (!payloads.length) return;
      const tooLarge = payloads.find((file) => file.size > SESSION_ATTACHMENT_MAX_BYTES);
      if (tooLarge) {
        throw new Error(`${tooLarge.fileName} 超过 20MB，请改用当前工作区文件管理上传。`);
      }
      const attachments = await Promise.all(payloads.map((payload) => {
        const file = fileFromPrivateWorkspacePayload(payload);
        return makeLocalPendingAttachment(file, "private_workspace", payload);
      }));
      setPendingAttachments((current) => [...current, ...attachments]);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "本机文件读取失败。");
    } finally {
      setIsUploadingAttachments(false);
    }
  }

  async function handleRemovePendingAttachment(attachment: PendingSessionAttachment) {
    if (isUploadedPendingAttachment(attachment)) {
      try {
        await deleteSessionAttachment(apiOptions, attachment.session_id, attachment.id);
      } catch {
        // Ignore stale attachment cleanup errors in the composer.
      }
    }
    revokeAttachmentPreviews([attachment]);
    const key = pendingAttachmentKey(attachment);
    setPendingAttachments((current) => current.filter((item) => pendingAttachmentKey(item) !== key));
  }

  function authorizeLocalPrivateAttachments() {
    const privateWorkspaceIds = pendingAttachments
      .map((attachment) => attachment.private_workspace_file_id)
      .filter((id): id is string => Boolean(id));
    if (privateWorkspaceIds.length) {
      window.projectR?.privateWorkspace?.setAuthorization({ ids: privateWorkspaceIds, status: "authorized" }).catch(() => {});
    }
    setPendingAttachments((current) =>
      current.map((attachment) =>
        isLocalPrivatePendingAttachment(attachment)
          ? { ...attachment, authorization_status: "authorized" }
          : attachment,
      ),
    );
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function uploadPendingAttachmentForSend(attachment: PendingSessionAttachment, sessionId: number) {
    if (isUploadedPendingAttachment(attachment)) {
      return attachment;
    }
    if (!attachment.file) {
      throw new Error(`本地附件已失效，请重新选择：${attachment.original_name}`);
    }
    let uploaded: PendingSessionAttachment;
    if (mode === "chat" && (attachment.kind === "text" || (attachment.kind === "pdf" && attachment.preprocess?.excerpt))) {
      const excerpt = attachment.preprocess?.excerpt ?? await readTextAttachmentExcerpt(attachment.file);
      const response = await createSessionAttachment(apiOptions, sessionId, {
        filename: attachment.original_name,
        content: excerpt || `[本机选择文件为空或无法读取：${attachment.original_name}]`,
        content_type: "text/plain",
        source_scope: attachment.private_workspace_file_id ? "local_private" : "session_upload",
        source_label: attachment.private_workspace_file_id ? "本机选择" : "会话临时上传",
        authorization_status: "uploaded",
      });
      uploaded = makeUploadedPendingAttachment(response, attachment.file, attachment);
    } else {
      const response = await uploadSessionAttachmentFile(apiOptions, sessionId, attachment.file, {
        source_scope: attachment.private_workspace_file_id ? "local_private" : "session_upload",
        source_label: attachment.private_workspace_file_id ? "本机选择" : "会话临时上传",
        authorization_status: "uploaded",
      });
      uploaded = makeUploadedPendingAttachment(response, attachment.file, attachment);
    }
    if (attachment.private_workspace_file_id) {
      window.projectR?.privateWorkspace?.setAuthorization({ ids: [attachment.private_workspace_file_id], status: "uploaded" }).catch(() => {});
    }
    return uploaded;
  }

  function handleComposerPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const files = filesFromClipboard(event.clipboardData);
    if (!files.length) return;
    event.preventDefault();
    void handleSelectAttachmentFiles(files, "paste");
  }

  function handleAttachmentDragEnter(event: DragEvent<HTMLDivElement>, pane: SplitPaneKey) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    setAttachmentDragTargetPane(pane);
  }

  function handleAttachmentDragOver(event: DragEvent<HTMLDivElement>, pane: SplitPaneKey) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setAttachmentDragTargetPane(pane);
  }

  function handleAttachmentDragLeave(event: DragEvent<HTMLDivElement>, pane: SplitPaneKey) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    const currentTarget = event.currentTarget;
    const relatedTarget = event.relatedTarget;
    if (relatedTarget instanceof Node && currentTarget.contains(relatedTarget)) return;
    if (attachmentDragTargetPane === pane) {
      setAttachmentDragTargetPane(null);
    }
  }

  function handleAttachmentDrop(
    event: DragEvent<HTMLDivElement>,
    pane: SplitPaneKey,
    paneSessionId: number | null,
  ) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    setAttachmentDragTargetPane(null);
    activateConversationPane(pane, paneSessionId);
    void handleSelectAttachmentFiles(Array.from(event.dataTransfer.files), "drop", { sessionId: paneSessionId, pane });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (skillPanelVisible) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (slashCandidates.length > 0) setSkillPanelIndex((i) => (i + 1) % slashCandidates.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (slashCandidates.length > 0) setSkillPanelIndex((i) => (i - 1 + slashCandidates.length) % slashCandidates.length);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        if (slashCandidates.length > 0) {
          insertSlashCandidate(slashCandidates[skillPanelIndex]);
        }
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setSkillPanelVisible(false);
        setSlashCommand(null);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  function handleSelectTab(id: string) {
    setShowScratchPad(false);
    setActiveTabId(id);
    const tab = tabs.find((item) => item.id === id);
    if (tab?.sessionId) {
      setActiveSessionId(tab.sessionId);
      if (sideBySideOpen) {
        setSplitPaneSessionIds((current) => ({ ...current, [activeSplitPane]: tab.sessionId ?? null }));
      }
      if (tab.workspaceId && tab.workspaceId !== activeWorkspaceId) {
        setActiveWorkspaceId(tab.workspaceId);
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

  function handleSwitchToAgent(_messageId: number) {
    setMode("agent");
  }

  function handleSelectPrompt(prompt: PromptOption) {
    const promptId = getPromptOptionId(prompt);
    if (!activeSessionId) {
      setPendingPromptId(promptId);
      setUtilityPanel(null);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    storePromptSelection(activeSessionId, promptId);
    setUtilityPanel(null);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function handleCreateUserPrompt(name: string, content: string) {
    const saved = await window.projectR?.prompts?.saveUser({ name, content });
    if (!saved) return;
    setUserPrompts((prev) => [saved, ...prev.filter((item) => item.id !== saved.id)]);
  }

  async function handleDeleteUserPrompt(id: string) {
    const next = await window.projectR?.prompts?.deleteUser(id);
    setUserPrompts(next ?? []);
    if (activeSessionId && promptSelections[String(activeSessionId)] === makePromptId("user", id)) {
      handleSelectPrompt(PROJECT_R_BUILTIN_PROMPT);
    }
    if (pendingPromptId === makePromptId("user", id)) {
      setPendingPromptId(null);
    }
  }

  function handleToggleSideBySide() {
    setSideBySideOpen((current) => {
      if (!current) {
        setActiveSplitPane("left");
        setSplitPaneSessionIds((paneIds) => ({
          left: paneIds.left ?? activeSessionId,
          right: paneIds.right === activeSessionId ? null : paneIds.right,
        }));
      }
      return !current;
    });
  }

  function activateConversationPane(pane: SplitPaneKey, sessionId: number | null) {
    setActiveSplitPane(pane);
    if (sessionId) {
      setActiveSessionId(sessionId);
      setActiveTabId(`chat-${sessionId}`);
    } else {
      setActiveSessionId(null);
      setActiveTabId("");
    }
  }

  function handleSelectSkillFromSidePanel(skill: SkillResponse) {
    setSelectedSkill(skill);
    setSelectedBuiltinCommand(null);
    if (mode === "chat" && skill.outputs.length > 0) {
      setMode("agent");
    }
    setUtilityPanel(null);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  const conversationPaneController = {
    activeSessionId,
    activeSplitPane,
    activeWorkspace,
    apiOptions,
    attachmentDragTargetPane,
    copiedMessageId,
    currentUser,
    draft,
    editingDraft,
    editingMessageId,
    fileInputRef,
    formatClockTime,
    formatSessionDisplayTitle,
    handleActivateVersion,
    handleAttachmentDragEnter,
    handleAttachmentDragLeave,
    handleAttachmentDragOver,
    handleAttachmentDrop,
    handleCancelSend,
    handleChoosePrivateWorkspaceFiles,
    handleComposerPaste,
    handleCopyMessage,
    handleKeyDown,
    handlePinSession,
    handleRemovePendingAttachment,
    handleRenameSession,
    handleSelectAttachmentFiles,
    handleSubmitEditedMessage,
    handleSubmitGBrainThinkReview,
    handleSwitchToAgent,
    handleToggleSideBySide,
    messageActionBusyId,
    messagesBySession,
    mode,
    openFeedbackDialog,
    openRegenerateDialog,
    renameInput,
    renderAvatar,
    requestDeleteMessageContext,
    scrollRef,
    serverUrl,
    sessions,
    sendingSessions,
    setDeleteConfirmSessionId,
    setDraft,
    setEditingDraft,
    setEditingMessageId,
    setRenameInput,
    setSourcePreview,
    setUtilityPanel,
    sideBySideOpen,
    splitPaneSessionIds,
    startEditingMessage,
    titleInputRef,
    token,
    utilityPanel,
    attachmentSourceLabel,
    authorizeLocalPrivateAttachments,
    clearPromptSelection,
    clearSelectedSkillIfMissing,
    composerRef,
    formatAttachmentSize,
    getSkillScopeLabel,
    handleSend,
    insertSlashCandidate,
    isLocalPrivatePendingAttachment,
    isUploadingAttachments,
    modelConfigError,
    modelMenuOpen,
    modelOptions,
    modelsLoading,
    modelSelectRef,
    pendingAttachmentKey,
    pendingAttachmentSendFormLabel,
    pendingAttachmentStatusLabel,
    pendingAttachmentTargetLabel,
    pendingAttachments,
    selectedBuiltinCommand,
    selectedModelOption,
    selectedPrompt,
    selectedPromptIsDefault,
    selectedSkill,
    setModelMenuOpen,
    setSelectedBuiltinCommand,
    setSelectedModelKey,
    setSelectedSkill,
    setSkillPanelIndex,
    setThinkingEnabled,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
    syncSlashCommand,
    textareaRef,
    thinkingEnabled,
    toggleWebSearch,
    webSearchEnabled,
  };

  function renderConversationPane(pane: SplitPaneKey) {
    return <ChatConversationPane controller={{ ...conversationPaneController, pane }} />;
  }
  return (
    <AppWorkspaceChrome
      controller={{
        UPDATE_DOWNLOAD_DRY_RUN,
        actionNotice,
        activeSessionId,
        activeTabId,
        activeWorkspace,
        activeWorkspaceId,
        apiOptions,
        auxiliaryPanelMaxWidth,
        auxiliaryPanelRef,
        auxiliaryPanelResizing,
        auxiliaryPanelWidth,
        availableUpdate,
        commitRename,
        companyPrompts,
        contextMenu,
        currentUser,
        clientVersion,
        deleteConfirmSessionId,
        deleteLastMessageTarget,
        deleteMessageTarget,
        deletedMessageUndo,
        downloadedUpdatePath,
        error,
        feedbackComment,
        feedbackRating,
        feedbackTarget,
        formatNotificationTime,
        formatSessionDisplayTitle,
        formatSidebarTime,
        formatUpdateBytes,
        formatUpdateSpeed,
        getInitials,
        getSkillScopeLabel,
        handleArchiveRestored,
        handleAuxiliaryPanelResizeStart,
        handleCloseTab,
        handleCreateSession,
        handleCreateUserPrompt,
        handleDeleteMessageContext,
        handleDeleteSession,
        handleDeleteUserPrompt,
        handleLogout,
        handleMarkAllNotificationsRead,
        handleMoveSession,
        handleNotificationAction,
        handleNotificationActionStatus,
        handleOpenScratch,
        handleReferenceWorkspaceFile,
        handleRegenerateMessage,
        handleSelectPrompt,
        handleSelectSkillFromSidePanel,
        handleSelectTab,
        handleSubmitFeedback,
        handleSidebarResizeStart,
        handleUndoDeleteMessages,
    handleWorkspaceChanged,
    handleWorkspaceFilePreviewClose,
    handleWorkspaceFilePreviewOpen,
        handleWorkspacePanelResizeStart,
        isLoading,
        messageActionBusyId,
        mode,
        modelOptions,
        moveSessionId,
        notificationButtonRef,
        notificationCategoryLabel,
        notificationPanelOpen,
        notificationPanelRef,
        notificationToast,
        notificationView,
        notifications,
        notificationsLoading,
        openSessionMenu,
        pendingNotificationCount,
        regenerateModelKey,
        regenerateModelOption,
        regenerateTarget,
        renderConversationPane,
        renameInput,
        resolveAvatarUrl,
        searchResults,
        searchTerm,
        selectedPromptId,
        selectSession,
        serverUrl,
        sessionGroups,
        sessions,
        setSourcePreview,
        setActiveMode: setMode,
        setContextMenu,
        setDeleteConfirmSessionId,
        setDeleteLastMessageTarget,
        setDeleteMessageTarget,
        setFeedbackComment,
        setFeedbackRating,
        setFeedbackTarget,
        setMoveSessionId,
        setNotificationPanelOpen,
        setNotificationView,
        setRegenerateModelKey,
        setRegenerateTarget,
        setRenameInput,
        setSearchTerm,
        setSettingsInitialAdminTab,
        setShowScratchPad,
        setShowSearch,
        setShowSettings,
        setUpdateDialogOpen,
        setUpdateStep,
        setUtilityPanel,
        settingsInitialAdminTab,
        showScratchPad,
        showSearch,
        showSettings,
        sideBySideOpen,
        skills,
        sidebarRef,
        sidebarRenameInputRef,
        sidebarResizing,
        sidebarWidth,
        splitPaneSessionIds,
        startClientUpdateDownload,
        sourcePreview,
        tabs,
        unreadNotificationCount,
        updateDialogOpen,
        updateError,
        updateProgress,
        updateStep,
        userPrompts,
        utilityPanel,
        workspacePanelMaxWidth,
        workspacePanelRef,
        workspacePanelResizing,
        workspacePanelWidth,
        workspaces,
      }}
    />
  );
}
