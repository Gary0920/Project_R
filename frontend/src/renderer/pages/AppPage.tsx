import { ClipboardEvent, DragEvent, KeyboardEvent, MouseEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";

import { ApiError, type ApiClientOptions } from "../api/client";
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
} from "../api/chat";
import { getLLMHealth } from "../api/health";
import {
  getNotificationCounts,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationView,
  updateNotificationActionStatus,
} from "../api/notifications";
import { listCompanyPrompts } from "../api/prompts";
import { listSkills } from "../api/skills";
import { getLatestClientUpdate } from "../api/updates";
import { fetchWorkspaceFileBlob, uploadWorkspaceFiles } from "../api/workspaces";
import { authTokenAtom, clearAuthAtom, currentUserAtom } from "../atoms/auth-atoms";
import { parseApiDate } from "../utils/time";
import {
  activeMessagesAtom,
  activeSessionAtom,
  activeSessionIdAtom,
  chatErrorAtom,
  chatLoadingAtom,
  chatMessagesBySessionAtom,
  chatSessionsAtom,
  type ChatMessage,
} from "../atoms/chat-atoms";
import { serverUrlAtom } from "../atoms/server-atoms";
import { activeModeAtom } from "../atoms/ui-atoms";
import { activeTabIdAtom, tabsAtom } from "../atoms/tab-atoms";
import { activeWorkspaceIdAtom, workspacesAtom } from "../atoms/workspace-atoms";
import { notificationsAtom, pendingNotificationCountAtom, unreadNotificationCountAtom } from "../atoms/notification-atoms";
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
} from "../api/types";
import { APP_NAME } from "../constants/app";
import { useContextMenu, type ContextMenuItemDef } from "../components/ContextMenu";
import { getPromptOptionId, PromptPanel, type PromptOption } from "../components/PromptPanel";
import { ScratchPad } from "../components/ScratchPad";
import { SearchDialog } from "../components/SearchDialog";
import { SettingsModal } from "../components/SettingsModal";
import { TabBar } from "../components/TabBar";
import { WorkspaceSelector } from "../components/WorkspaceSelector";
import { WorkspaceFilePanel } from "../components/WorkspaceFilePanel";
import { PROJECT_R_BUILTIN_PROMPT } from "../constants/prompts";
import {
  AgentIcon,
  BellIcon,
  BrainIcon,
  ChatIcon,
  ChevronDownIcon,
  CopyIcon,
  EditIcon,
  GlobeIcon,
  LogoutIcon,
  MoreIcon,
  MoveIcon,
  PaperclipIcon,
  PinIcon,
  PlusIcon,
  PromptIcon,
  RefreshIcon,
  SearchIcon,
  SendIcon,
  SettingsIcon,
  SplitIcon,
  StopIcon,
  TrashIcon,
  WorkspaceIcon,
  XmarkIcon,
} from "../components/LineIcons";

type SplitPaneKey = "left" | "right";
type UtilityPanel = "workspace" | "prompt" | "skills" | "source";
type RenameScope = "header" | "sidebar";
type SettingsAdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type ClientUpdateStep = "available" | "downloading" | "installing" | "ready" | "failed";
type SourcePreview = {
  index: number;
  source: ChatSourceResponse;
  sessionId?: number | null;
};

type AttachmentInputSource = "picker" | "paste" | "drop" | "private_workspace" | "workspace_reference";
type AttachmentSourceScope = "local_private" | "session_upload";
type AttachmentAuthorizationStatus = "pending" | "authorized" | "uploaded";
type PendingSessionAttachment = Omit<SessionAttachmentResponse, "session_id"> & {
  local_id: string;
  session_id: number | null;
  kind: "image" | "pdf" | "text" | "file";
  previewUrl?: string;
  file?: File;
  sha256?: string | null;
  relative_path?: string | null;
  private_workspace_file_id?: string | null;
  preprocess?: PrivateWorkspacePreprocessResult | null;
  source_scope: AttachmentSourceScope;
  source_label: string;
  authorization_status: AttachmentAuthorizationStatus;
  input_source: AttachmentInputSource;
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

const FALLBACK_CLIENT_VERSION = "0.1.0";
const UPDATE_DOWNLOAD_DRY_RUN = import.meta.env.DEV || import.meta.env.VITE_UPDATE_DRY_RUN === "1";

const SESSION_ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024;
const LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS = 12000;
const PASTED_IMAGE_EXTENSION_BY_TYPE: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/bmp": "bmp",
};

function getAttachmentKind(fileName: string, contentType: string): PendingSessionAttachment["kind"] {
  const normalizedType = contentType.toLowerCase();
  const normalizedName = fileName.toLowerCase();
  if (normalizedType.startsWith("image/")) return "image";
  if (normalizedType === "application/pdf" || normalizedName.endsWith(".pdf")) return "pdf";
  if (normalizedType.startsWith("text/") || /\.(txt|md|markdown|csv|json|yaml|yml|log|html|css|js|ts|tsx|py)$/i.test(normalizedName)) {
    return "text";
  }
  return "file";
}

function formatAttachmentSize(size: number) {
  if (size < 1024) return `${size}B`;
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)}KB`;
  return `${(size / 1024 / 1024).toFixed(1)}MB`;
}

function makeLocalAttachmentId() {
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `local-${Date.now()}-${randomPart}`;
}

function pendingAttachmentKey(attachment: PendingSessionAttachment) {
  return attachment.local_id || `server-${attachment.id}`;
}

function isLocalPrivatePendingAttachment(attachment: PendingSessionAttachment) {
  return attachment.source_scope === "local_private";
}

function isUploadedPendingAttachment(attachment: PendingSessionAttachment): attachment is PendingSessionAttachment & { session_id: number; id: number } {
  return attachment.authorization_status === "uploaded" && attachment.session_id !== null && attachment.id > 0;
}

function attachmentSourceLabel(attachment: { source_label?: string; source_scope?: string }) {
  if (attachment.source_label) return attachment.source_label;
  if (attachment.source_scope === "local_private") return "本机选择";
  if (attachment.source_scope === "project") return "项目资料";
  if (attachment.source_scope === "company") return "公司知识库";
  return "会话临时上传";
}

function pendingAttachmentStatusLabel(attachment: PendingSessionAttachment) {
  if (attachment.source_scope !== "local_private") {
    return attachment.authorization_status === "uploaded" ? "已附加" : "可直接发送";
  }
  return attachment.authorization_status === "authorized" ? "已确认" : "待确认";
}

function pendingAttachmentSendFormLabel(attachment: PendingSessionAttachment, mode: string) {
  if (mode === "chat" && attachment.preprocess?.sendForm === "excerpt") return "发送摘录";
  if (mode === "chat" && attachment.kind === "text") return "发送摘录";
  if (mode === "chat" && attachment.kind === "pdf" && attachment.preprocess?.extractionStatus === "pdf_text_unavailable") return "上传 PDF 原文件";
  if (mode === "chat" && attachment.kind === "image") return "上传图片给模型";
  if (mode === "agent") return "上传临时文件";
  return "上传临时文件";
}

function pendingAttachmentTargetLabel(mode: string) {
  return mode === "agent" ? "Agent 临时任务" : "Chat 会话";
}

async function hashFileSha256(file: File) {
  if (!window.crypto?.subtle) return null;
  try {
    const digest = await window.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    return null;
  }
}

async function readTextAttachmentExcerpt(file: File) {
  const text = await file.text();
  const normalized = text.trim();
  if (normalized.length <= LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS) return normalized;
  return `${normalized.slice(0, LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS)}\n\n[本机选择文件摘录已截断，仅发送前 ${LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS} 个字符。]`;
}

function fileFromPrivateWorkspacePayload(payload: PrivateWorkspaceFilePayload) {
  const binary = atob(payload.base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new File([bytes], payload.fileName, {
    type: payload.contentType || "application/octet-stream",
    lastModified: new Date(payload.updatedAt).getTime() || Date.now(),
  });
}

function makePastedAttachmentName(file: File, index: number) {
  if (file.name && file.name !== "image.png") return file.name;
  const extension = PASTED_IMAGE_EXTENSION_BY_TYPE[file.type] ?? "png";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `pasted-image-${stamp}-${index + 1}.${extension}`;
}

function normalizePastedFile(file: File, index: number) {
  const name = makePastedAttachmentName(file, index);
  if (file.name === name) return file;
  return new File([file], name, { type: file.type || "application/octet-stream", lastModified: file.lastModified || Date.now() });
}

function filesFromClipboard(data: DataTransfer) {
  const directFiles = Array.from(data.files ?? []);
  if (directFiles.length) {
    return directFiles.map(normalizePastedFile);
  }
  return Array.from(data.items ?? [])
    .filter((item) => item.kind === "file")
    .map((item, index) => {
      const file = item.getAsFile();
      return file ? normalizePastedFile(file, index) : null;
    })
    .filter((file): file is File => Boolean(file));
}

function hasFileTransfer(data: DataTransfer | null) {
  if (!data) return false;
  return Array.from(data.types ?? []).includes("Files") || Array.from(data.items ?? []).some((item) => item.kind === "file");
}

function isAudioVideoAttachment(attachment: PendingSessionAttachment) {
  const contentType = (attachment.content_type || "").toLowerCase();
  return contentType.startsWith("audio/") || contentType.startsWith("video/");
}

function formatClockTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parseApiDate(value));
}

function formatSidebarTime(value: string) {
  const date = parseApiDate(value);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 0) return "刚刚";

  const diffMinutes = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMinutes < 60) {
    return diffMinutes <= 0 ? "刚刚" : `${diffMinutes}分钟`;
  }
  if (diffHours < 24) {
    return `${diffHours}小时`;
  }
  if (diffDays < 7) {
    return `${diffDays}天`;
  }
  return "1周";
}

function formatNotificationTime(value: string) {
  const date = parseApiDate(value);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 60_000) return "刚刚";
  if (diffMs < 3_600_000) return `${Math.max(1, Math.floor(diffMs / 60_000))}分钟前`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}小时前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

function notificationCategoryLabel(category: NotificationResponse["category"]) {
  return {
    system: "系统",
    task: "任务",
    workspace: "项目",
    approval: "审批",
    risk: "风险",
  }[category];
}

function shouldToastNotification(notification: NotificationResponse) {
  if (notification.category === "risk" && notification.severity === "critical") return true;
  if (notification.category === "task" && (notification.severity === "success" || notification.severity === "warning")) return true;
  return false;
}

function numericPayloadValue(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringPayloadValue(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function formatUpdateBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatUpdateSpeed(bytesPerSecond: number) {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return "";
  return `${formatUpdateBytes(bytesPerSecond)}/s`;
}

function groupSessionsByTime(sessions: ChatSessionResponse[]) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400_000;

  const today: ChatSessionResponse[] = [];
  const yesterday: ChatSessionResponse[] = [];
  const earlier: ChatSessionResponse[] = [];

  for (const session of sessions) {
    const d = parseApiDate(session.updated_at);
    const dayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    if (dayStart === startOfToday) {
      today.push(session);
    } else if (dayStart === startOfYesterday) {
      yesterday.push(session);
    } else {
      earlier.push(session);
    }
  }

  const groups: { key: string; label: string | null; items: ChatSessionResponse[] }[] = [];
  if (today.length) groups.push({ key: "today", label: "今天", items: today });
  if (yesterday.length) groups.push({ key: "yesterday", label: "昨天", items: yesterday });
  if (earlier.length) groups.push({ key: "earlier", label: "更早", items: earlier });
  return groups;
}

function makeSessionTitle(content: string) {
  const compact = content
    .replace(/^\s*\/query\s+/i, "")
    .replace(/^\s*\/[A-Za-z0-9_-]+\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!compact) return "新对话";
  return compact.length > 24 ? `${compact.slice(0, 24)}...` : compact;
}

function formatSessionDisplayTitle(title: string) {
  const compact = title
    .replace(/^\s*\/query\s+/i, "")
    .replace(/^\s*\/[A-Za-z0-9_-]+\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
  return compact || title;
}

function getInitials(name: string | undefined | null) {
  const trimmed = name?.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : "U";
}

function resolveAvatarUrl(baseUrl: string, avatar: string | undefined | null) {
  if (!avatar) return "";
  if (avatar.startsWith("http") || avatar.startsWith("data:")) return avatar;
  if (avatar.startsWith("/")) return `${baseUrl.replace(/\/$/, "")}${avatar}`;
  return "";
}

function renderAvatar(avatar: string | undefined, nickname: string | undefined | null, size = 22, baseUrl = "") {
  const imageUrl = resolveAvatarUrl(baseUrl, avatar);
  return (
    <span
      className={`message-avatar ${!imageUrl && !avatar ? "is-text" : ""}`}
      style={{ width: size, height: size, fontSize: size * 0.55 }}
    >
      {imageUrl ? (
        <img src={imageUrl} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : (
        avatar || getInitials(nickname)
      )}
    </span>
  );
}

type SlashCommandMatch = {
  start: number;
  end: number;
  query: string;
};

type BuiltinSlashCommand = {
  kind: "command";
  name: string;
  displayName: string;
  description: string;
  insertText: string;
  scope: string;
  aliases: string[];
};

type SkillSlashCandidate =
  | { kind: "command"; command: BuiltinSlashCommand; score: number }
  | { kind: "skill"; skill: SkillResponse; score: number };

const BUILTIN_SLASH_COMMANDS: BuiltinSlashCommand[] = [
  {
    kind: "command",
    name: "query",
    displayName: "查询知识库",
    description: "使用 GBrain 检索公司知识库和当前项目知识库，并返回引用来源。",
    insertText: "/query ",
    scope: "GBrain",
    aliases: ["query", "知识库", "查询", "gbrain", "ask"],
  },
];

function findSlashCommand(text: string, caret: number): SlashCommandMatch | null {
  const beforeCaret = text.slice(0, caret);
  const match = /(?:^|\n)[ \t]*\/([^\n]*)$/.exec(beforeCaret);
  if (!match || match.index === undefined) return null;
  const slashOffset = beforeCaret.slice(match.index).indexOf("/");
  if (slashOffset < 0) return null;
  return {
    start: match.index + slashOffset,
    end: caret,
    query: match[1].trim().toLowerCase(),
  };
}

function fuzzyScore(value: string, query: string) {
  const source = value.toLowerCase();
  const needle = query.trim().toLowerCase();
  if (!needle) return 1;
  if (source.includes(needle)) return 100 - source.indexOf(needle);

  let score = 0;
  let sourceIndex = 0;
  let streak = 0;
  for (const char of needle) {
    const found = source.indexOf(char, sourceIndex);
    if (found === -1) return 0;
    streak = found === sourceIndex ? streak + 1 : 1;
    score += 8 + streak * 3 - Math.min(found - sourceIndex, 8);
    sourceIndex = found + 1;
  }
  return score;
}

function scoreSkill(skill: SkillResponse, query: string) {
  const fields = [
    skill.display_name,
    skill.name,
    skill.description,
    skill.category,
    ...skill.trigger,
  ];
  return Math.max(...fields.map((field) => fuzzyScore(String(field ?? ""), query)));
}

function scoreBuiltinSlashCommand(command: BuiltinSlashCommand, query: string) {
  const fields = [
    command.name,
    command.displayName,
    command.description,
    command.scope,
    ...command.aliases,
  ];
  return Math.max(...fields.map((field) => fuzzyScore(String(field ?? ""), query)));
}

function getSkillScopeLabel(skill: SkillResponse) {
  const path = skill.path.toLowerCase();
  if (path.includes("/personal/") || path.includes("/user/")) return "个人";
  return "Skills";
}

const PROMPT_SELECTION_KEY = "project_r_session_prompt_selection";
const SETTINGS_PREFERENCES_KEY = "project-r:settings-preferences";
const SIDEBAR_WIDTH_KEY = "project-r:chat-sidebar-width";
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_DEFAULT_WIDTH = 268;
const SIDEBAR_MAX_WIDTH = 420;
const WORKSPACE_PANEL_WIDTH_KEY = "project-r:workspace-panel-width";
const WORKSPACE_PANEL_MIN_WIDTH = 320;
const WORKSPACE_PANEL_DEFAULT_WIDTH = 640;
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

function markdownToPlainText(value: string) {
  return value
    .replace(/```[a-zA-Z0-9_-]*\n([\s\S]*?)```/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/[*_~]{1,3}/g, "")
    .trim();
}

async function copyText(value: string, cleanMarkdown = false) {
  const text = cleanMarkdown ? markdownToPlainText(value) : value;
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // Fall back to the legacy copy path below. Some embedded browsers deny Clipboard API.
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!ok) {
    throw new Error("Clipboard copy failed");
  }
}

async function downloadGeneratedFile(baseUrl: string, token: string | null, file: GeneratedFileResponse) {
  const response = await fetch(`${baseUrl}${file.download_url}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error("文件下载失败");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function generatedFileKindLabel(file: GeneratedFileResponse) {
  const mime = (file.mime_type || "").toLowerCase();
  const name = (file.filename || "").toLowerCase();
  if (mime.includes("word") || name.endsWith(".docx")) return "已生成 Word 文档";
  if (mime.includes("spreadsheet") || name.endsWith(".xlsx")) return "已生成 Excel 文件";
  if (mime.includes("presentation") || name.endsWith(".pptx")) return "已生成演示文稿";
  if (mime.includes("pdf") || name.endsWith(".pdf")) return "已生成 PDF 文件";
  return "已生成文件";
}

function renderGeneratedFileCard(file: GeneratedFileResponse, onDownload: (file: GeneratedFileResponse) => void) {
  return (
    <div className="message-file-card">
      <div>
        <strong>{file.filename}</strong>
        <span>{generatedFileKindLabel(file)}</span>
      </div>
      <button
        className="message-file-download"
        onClick={() => onDownload(file)}
        type="button"
      >
        下载
      </button>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function isImageAttachmentResponse(attachment: SessionAttachmentResponse) {
  return (attachment.content_type || "").toLowerCase().startsWith("image/");
}

function attachmentKindLabel(attachment: SessionAttachmentResponse) {
  const kind = getAttachmentKind(attachment.original_name, attachment.content_type || "");
  if (kind === "image") return "IMG";
  if (kind === "pdf") return "PDF";
  if (kind === "text") return "TXT";
  return "FILE";
}

function MessageAttachments({
  attachments,
  apiOptions,
}: {
  attachments?: SessionAttachmentResponse[];
  apiOptions: ApiClientOptions;
}) {
  const visibleAttachments = attachments ?? [];
  if (!visibleAttachments.length) return null;
  return (
    <div className={`message-attachments ${visibleAttachments.length === 1 ? "is-single" : ""}`}>
      {visibleAttachments.map((attachment) =>
        isImageAttachmentResponse(attachment) ? (
          <MessageAttachmentImage attachment={attachment} apiOptions={apiOptions} key={attachment.id} />
        ) : (
          <MessageAttachmentFile attachment={attachment} apiOptions={apiOptions} key={attachment.id} />
        ),
      )}
    </div>
  );
}

function MessageAttachmentImage({
  attachment,
  apiOptions,
}: {
  attachment: SessionAttachmentResponse;
  apiOptions: ApiClientOptions;
}) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setImageUrl(null);
    setLoadFailed(false);
    fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setLoadFailed(true);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [apiOptions.baseUrl, apiOptions.token, apiOptions.onUnauthorized, attachment.id, attachment.session_id]);

  useEffect(() => {
    if (!previewOpen) return;
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setPreviewOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [previewOpen]);

  return (
    <>
      <button
        className={`message-attachment-image ${loadFailed ? "is-failed" : ""}`}
        disabled={!imageUrl}
        onClick={() => imageUrl ? setPreviewOpen(true) : undefined}
        title={imageUrl ? `点击预览图片 · ${attachmentSourceLabel(attachment)}` : attachment.original_name}
        type="button"
      >
        {imageUrl ? (
          <>
            <img alt={attachment.original_name} src={imageUrl} />
            <span className="message-attachment-image-source">{attachmentSourceLabel(attachment)}</span>
          </>
        ) : (
          <span>{loadFailed ? "图片加载失败" : "图片加载中"}</span>
        )}
      </button>
      {previewOpen && imageUrl ? (
        <div className="attachment-lightbox-backdrop" onClick={() => setPreviewOpen(false)} role="presentation">
          <div className="attachment-lightbox" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <button className="attachment-lightbox-close" onClick={() => setPreviewOpen(false)} title="关闭预览" type="button">
              <XmarkIcon />
            </button>
            <img alt={attachment.original_name} src={imageUrl} />
            <div className="attachment-lightbox-footer">
              <span>{attachment.original_name} · {attachmentSourceLabel(attachment)}</span>
              <button
                onClick={() => void fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id)
                  .then((blob) => downloadBlob(blob, attachment.original_name))
                  .catch(() => {})}
                type="button"
              >
                下载
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function MessageAttachmentFile({
  attachment,
  apiOptions,
}: {
  attachment: SessionAttachmentResponse;
  apiOptions: ApiClientOptions;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const kind = getAttachmentKind(attachment.original_name, attachment.content_type || "");
  const canPreview = kind === "pdf" || kind === "text";
  const sourceLabel = attachmentSourceLabel(attachment);
  async function handleOpenAttachment() {
    setBusy(true);
    setFailed(false);
    try {
      const blob = await fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id);
      if (canPreview) {
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank", "noopener,noreferrer");
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } else {
        downloadBlob(blob, attachment.original_name);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      className="message-attachment-file"
      disabled={busy}
      onClick={() => void handleOpenAttachment()}
      title={failed ? "附件打开失败" : canPreview ? "打开预览" : "下载附件"}
      type="button"
    >
      <span className={`message-attachment-file-kind is-${kind}`}>{attachmentKindLabel(attachment)}</span>
      <span className="message-attachment-file-main">
        <strong>{attachment.original_name}</strong>
        <small>{failed ? "打开失败" : `${sourceLabel} · ${formatAttachmentSize(attachment.size)} · ${canPreview ? "打开预览" : "下载"}`}</small>
      </span>
    </button>
  );
}

function renderSourceRefTag(
  label: string,
  index: number,
  key: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const source = sources?.[index - 1];
  const title = source
    ? `${source.source_title || source.file}\n${source.section_path || source.file}\n${source.content.slice(0, 120)}`
    : `来源 ${index}`;
  return (
    <button
      className="message-source-ref"
      disabled={!source}
      key={key}
      onClick={() => source ? onSelectSource?.({ index, source }) : undefined}
      title={title}
      type="button"
    >
      {label.includes("Doc") ? label : `[${index}]`}
    </button>
  );
}

function renderInlineMarkdown(
  text: string,
  keyPrefix: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[\[[^\]]+\]\]|[（(]\s*来源\s*\d+\s*[）)]|来源\s*\d+)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-strong-${match.index}`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code className="message-inline-code" key={`${keyPrefix}-code-${match.index}`}>{token.slice(1, -1)}</code>);
    } else if (/来源\s*\d+/.test(token)) {
      const sourceIndex = Number(token.match(/\d+/)?.[0] ?? "0");
      nodes.push(renderSourceRefTag(`[${sourceIndex}]`, sourceIndex, `${keyPrefix}-source-${match.index}`, sources, onSelectSource));
    } else {
      nodes.push(<span className="message-wikilink" key={`${keyPrefix}-wiki-${match.index}`}>{token}</span>);
    }
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function isMarkdownTable(lines: string[]) {
  return lines.length >= 2 && lines[0].includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[1]);
}

function renderMarkdownTable(
  lines: string[],
  key: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const parseRow = (line: string) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((cell) => cell.trim());
  const headers = parseRow(lines[0]);
  const rows = lines.slice(2).filter((line) => line.includes("|")).map(parseRow);
  return (
    <div className="message-table-wrap" key={key}>
      <table className="message-table">
        <thead>
          <tr>{headers.map((header, index) => <th key={`${key}-h-${index}`}>{renderInlineMarkdown(header, `${key}-h-${index}`, sources, onSelectSource)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${key}-r-${rowIndex}`}>
              {row.map((cell, cellIndex) => <td key={`${key}-r-${rowIndex}-${cellIndex}`}>{renderInlineMarkdown(cell, `${key}-r-${rowIndex}-${cellIndex}`, sources, onSelectSource)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderMarkdownText(
  text: string,
  keyPrefix: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const blocks = text.split(/\n{2,}/g).filter((block) => block.trim().length > 0);
  return blocks.map((block, blockIndex) => {
    const key = `${keyPrefix}-block-${blockIndex}`;
    const lines = block.split("\n").filter((line) => line.trim().length > 0);
    const firstLine = lines[0]?.trim() ?? "";

    if (isMarkdownTable(lines)) {
      return renderMarkdownTable(lines, key, sources, onSelectSource);
    }
    if (lines.every((line) => /^\s*-{3,}\s*$/.test(line))) {
      return <hr className="message-divider" key={key} />;
    }
    if (/^#{1,4}\s+/.test(firstLine)) {
      const level = Math.min(4, firstLine.match(/^#+/)?.[0].length ?? 3);
      const headingContent = renderInlineMarkdown(firstLine.replace(/^#{1,4}\s+/, ""), key, sources, onSelectSource);
      if (level === 1) return <h1 className="message-heading" key={key}>{headingContent}</h1>;
      if (level === 2) return <h2 className="message-heading" key={key}>{headingContent}</h2>;
      if (level === 3) return <h3 className="message-heading" key={key}>{headingContent}</h3>;
      return <h4 className="message-heading" key={key}>{headingContent}</h4>;
    }
    if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
      return (
        <ul className="message-list" key={key}>
          {lines.map((line, index) => <li key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*[-*]\s+/, ""), `${key}-${index}`, sources, onSelectSource)}</li>)}
        </ul>
      );
    }
    if (lines.every((line) => /^\s*\d+\.\s+/.test(line))) {
      return (
        <ol className="message-list" key={key}>
          {lines.map((line, index) => <li key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*\d+\.\s+/, ""), `${key}-${index}`, sources, onSelectSource)}</li>)}
        </ol>
      );
    }
    if (lines.every((line) => /^\s*>\s?/.test(line))) {
      return <blockquote className="message-quote" key={key}>{lines.map((line, index) => <p key={`${key}-${index}`}>{renderInlineMarkdown(line.replace(/^\s*>\s?/, ""), `${key}-${index}`, sources, onSelectSource)}</p>)}</blockquote>;
    }
    return (
      <p className="message-paragraph" key={key}>
        {lines.map((line, index) => (
          <span key={`${key}-${index}`}>
            {renderInlineMarkdown(line, `${key}-${index}`, sources, onSelectSource)}
            {index < lines.length - 1 ? <br /> : null}
          </span>
        ))}
      </p>
    );
  });
}

function renderMessageContent(
  content: string,
  sources?: ChatSourceResponse[],
  onSelectSource?: (preview: SourcePreview) => void,
) {
  const nodes: ReactNode[] = [];
  const pattern = /```([A-Za-z0-9_-]+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(content)) !== null) {
    const before = content.slice(lastIndex, match.index);
    if (before.trim()) {
      nodes.push(...renderMarkdownText(before, `text-${index}`, sources, onSelectSource));
    }
    const language = match[1]?.trim();
    const code = match[2].trim();
    nodes.push(
      <MessageCodeBlock code={code} key={`code-${index}`} language={language} />,
    );
    lastIndex = pattern.lastIndex;
    index += 1;
  }
  const rest = content.slice(lastIndex);
  if (rest.trim()) {
    nodes.push(...renderMarkdownText(rest, `text-${index}`, sources, onSelectSource));
  }
  return nodes;
}

function MessageCodeBlock({ code, language }: { code: string; language?: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (copyState === "idle") return;
    const timer = window.setTimeout(() => setCopyState("idle"), 1600);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  async function handleCopyCode() {
    try {
      await copyText(code);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <div className="message-code-block">
      <div className="message-code-toolbar">
        <span>{language || "可复制内容"}</span>
        <button
          className={`message-code-copy ${copyState !== "idle" ? `is-${copyState}` : ""}`}
          onClick={() => void handleCopyCode()}
          title={copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
          type="button"
        >
          {copyState === "copied" ? <span className="message-action-check">✓</span> : <CopyIcon />}
          {copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
        </button>
      </div>
      <pre className="message-code"><code>{code}</code></pre>
    </div>
  );
}

function renderSkillRunCard(
  skillRun: SkillRunResponse,
  options: {
    showGeneratedFile?: boolean;
    onDownloadGeneratedFile?: (file: GeneratedFileResponse) => void;
  } = {},
) {
  const missingFields = skillRun.missing_inputs
    .map((item) => String(item.label ?? item.name ?? "待补充字段"))
    .filter(Boolean);
  const dispatchSteps = Array.isArray(skillRun.dispatch?.steps) ? skillRun.dispatch.steps as Array<Record<string, unknown>> : [];
  return (
    <div className="message-skill-card">
      <div className="message-skill-header">
        <strong>{skillRun.skill?.display_name ?? skillRun.skill_name}</strong>
        <span>{skillRun.status === "completed" ? "已完成" : skillRun.status === "ready" ? "待执行" : skillRun.status === "failed" ? "失败" : "收集中"}</span>
      </div>
      {dispatchSteps.length ? (
        <div className="message-skill-dispatch">
          {dispatchSteps.map((step, index) => (
            <span key={`${String(step.id ?? index)}-${String(step.tool ?? "")}`}>
              {String(step.label ?? step.tool ?? "执行步骤")}
            </span>
          ))}
        </div>
      ) : null}
      {missingFields.length ? (
        <div className="message-skill-fields">
          {missingFields.map((field) => (
            <span key={field}>{field}</span>
          ))}
        </div>
      ) : null}
      {options.showGeneratedFile !== false && skillRun.generated_file && options.onDownloadGeneratedFile ? (
        renderGeneratedFileCard(skillRun.generated_file, options.onDownloadGeneratedFile)
      ) : skillRun.generated_file ? (
        <div className="message-skill-output">{skillRun.generated_file.filename}</div>
      ) : null}
    </div>
  );
}

function agentRunStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待输入";
  if (status === "queued") return "排队中";
  if (status === "cancelled") return "已取消";
  return "执行中";
}

function agentEventStatusLabel(status: string) {
  if (status === "completed") return "完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待";
  if (status === "queued") return "排队";
  return "进行中";
}

function renderAgentRunCard(agentRun: AgentRunResponse) {
  const events = agentRun.events ?? [];
  return (
    <div className={`message-agent-run-card is-${agentRun.status}`}>
      <div className="message-agent-run-header">
        <span className="message-agent-run-icon"><AgentIcon /></span>
        <div>
          <strong>{agentRun.title}</strong>
          <span>{agentRunStatusLabel(agentRun.status)}</span>
        </div>
      </div>
      {events.length ? (
        <ol className="message-agent-event-list">
          {events.map((event) => (
            <li className={`message-agent-event is-${event.status}`} key={event.id}>
              <span className="message-agent-event-dot" />
              <div>
                <div className="message-agent-event-title">
                  <strong>{event.title}</strong>
                  <small>{agentEventStatusLabel(event.status)}</small>
                </div>
                {event.detail ? <p>{event.detail}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      {agentRun.error_message ? <p className="message-agent-run-error">{agentRun.error_message}</p> : null}
    </div>
  );
}

function hasContextTrace(contextTrace: ChatContextTraceResponse | null | undefined) {
  if (!contextTrace) return false;
  return Boolean(
    contextTrace.attachments?.length ||
    contextTrace.knowledge?.source_count ||
    contextTrace.prompt?.selected_prompt_id ||
    contextTrace.prompt?.system_prompt_provided ||
    contextTrace.skill?.skill_name ||
    contextTrace.gbrain_think?.gap_count ||
    contextTrace.gbrain_think?.conflict_count ||
    contextTrace.gbrain_think?.warning_count ||
    contextTrace.model?.model,
  );
}

function renderContextTraceCard(
  contextTrace: ChatContextTraceResponse | null | undefined,
  options: { onSubmitGBrainThinkReview?: () => void; gbrainThinkReviewBusy?: boolean } = {},
) {
  if (!hasContextTrace(contextTrace) || !contextTrace) return null;
  const attachments = contextTrace.attachments ?? [];
  const sources = contextTrace.knowledge?.sources ?? [];
  const prompt = contextTrace.prompt;
  const model = contextTrace.model;
  const gbrainThink = contextTrace.gbrain_think;
  const gbrainGaps = gbrainThink?.gaps?.filter(Boolean) ?? [];
  const gbrainConflicts = gbrainThink?.conflicts?.filter(Boolean) ?? [];
  const gbrainWarnings = gbrainThink?.warnings?.filter(Boolean) ?? [];
  const modelBadges = [
    model?.model,
    model?.thinking ? "思考" : null,
    model?.web_search ? "联网搜索" : null,
  ].filter(Boolean).join(" · ");
  return (
    <div className="message-context-trace">
      <div className="message-context-trace-header">
        <strong>本轮上下文</strong>
        {modelBadges ? <span>{modelBadges}</span> : null}
      </div>
      <div className="message-context-trace-grid">
        {attachments.length ? (
          <div className="message-context-trace-section">
            <span>附件</span>
            {attachments.slice(0, 4).map((attachment) => (
              <small key={`${attachment.id}-${attachment.name}`}>{attachment.name ?? `附件 ${attachment.id}`}</small>
            ))}
            {attachments.length > 4 ? <small>另有 {attachments.length - 4} 个附件</small> : null}
          </div>
        ) : null}
        {sources.length || contextTrace.knowledge?.source_count ? (
          <div className="message-context-trace-section">
            <span>知识来源</span>
            {sources.slice(0, 4).map((source) => (
              <small key={`${source.index}-${source.file}`}>{source.section_path || source.source_title || source.file}</small>
            ))}
            {(contextTrace.knowledge?.source_count ?? 0) > sources.length ? (
              <small>共 {contextTrace.knowledge?.source_count} 个来源</small>
            ) : null}
          </div>
        ) : null}
        {gbrainThink && (gbrainGaps.length || gbrainConflicts.length || gbrainWarnings.length) ? (
          <div className="message-context-trace-section is-gbrain-think">
            <span>
              GBrain 推理状态
              {options.onSubmitGBrainThinkReview ? (
                <button
                  className="message-context-trace-action"
                  disabled={options.gbrainThinkReviewBusy}
                  onClick={options.onSubmitGBrainThinkReview}
                  type="button"
                >
                  {options.gbrainThinkReviewBusy ? "提交中" : "提交审核"}
                </button>
              ) : null}
            </span>
            {gbrainConflicts.map((item, index) => (
              <small className="is-conflict" key={`gbrain-conflict-${index}`}>冲突：{item}</small>
            ))}
            {gbrainGaps.map((item, index) => (
              <small className="is-gap" key={`gbrain-gap-${index}`}>缺口：{item}</small>
            ))}
            {gbrainWarnings.map((item, index) => (
              <small className="is-warning" key={`gbrain-warning-${index}`}>警告：{item}</small>
            ))}
          </div>
        ) : null}
        {(prompt?.selected_prompt_id || prompt?.system_prompt_provided || contextTrace.skill?.skill_name) ? (
          <div className="message-context-trace-section">
            <span>提示词 / Skill</span>
            {prompt?.selected_prompt_id ? <small>{prompt.selected_prompt_id}</small> : null}
            {contextTrace.skill?.display_name || contextTrace.skill?.skill_name ? (
              <small>{contextTrace.skill.display_name || contextTrace.skill.skill_name}</small>
            ) : null}
            {prompt?.system_prompt_provided ? <small>{prompt.system_prompt_preview || "已使用会话提示词"}</small> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
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
  const scrollRef = useRef<HTMLDivElement | null>(null);
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
      const currentVersion = await (window.projectR?.updates?.getCurrentVersion?.() ?? Promise.resolve(FALLBACK_CLIENT_VERSION));
      const platform = window.projectR?.platform ?? "win32";
      setClientVersion(currentVersion || FALLBACK_CLIENT_VERSION);
      const response = await getLatestClientUpdate(
        { baseUrl: serverUrl, token: null, onUnauthorized: undefined },
        currentVersion || FALLBACK_CLIENT_VERSION,
        platform,
      );
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
    const previewPanelWidth = clampWorkspacePanelWidth(WORKSPACE_PANEL_PREVIEW_WIDTH);
    setWorkspacePanelWidth((width) => Math.max(width, previewPanelWidth));
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
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
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

const WHIMSICAL_WORDS = [
    "Discombobulating", "Concocting", "Moonwalking", "Mulling",
    "Purring", "Doodling", "Pondering", "Exploring", "Discovering",
    "Brewing", "Unraveling", "Daydreaming", "Juggling",
    "Tinkering", "Marinating", "Orchestrating", "Harmonizing",
  "Contemplating", "Synthesizing", "Twiddling",
];

function getRandomWord(prev?: string): string {
    const pool = prev ? WHIMSICAL_WORDS.filter((w) => w !== prev) : WHIMSICAL_WORDS;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function LoadingPlaceholder() {
    const [word, setWord] = useState(() => getRandomWord());

    useEffect(() => {
      let prev = word;
      const interval = window.setInterval(() => {
        const next = getRandomWord(prev);
        prev = next;
        setWord(next);
      }, 2000);
      return () => window.clearInterval(interval);
    }, []);

    return (
      <article className="message-row message-row-assistant message-row-loading">
        <span className="message-avatar assistant-avatar is-text">R</span>
        <div className="message-body">
          <div className="message-meta">
            <div className="message-name-line">
              <span className="message-role-label">{APP_NAME}</span>
            </div>
          </div>
          <div className="message-bubble">
            <div className="loading-placeholder-inner">
              <svg className="pl" viewBox="0 0 128 128" width="128" height="128" xmlns="http://www.w3.org/2000/svg">
                <circle className="pl__ring pl__ring--a" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--b" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--c" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--d" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
              </svg>
              <span className="loading-placeholder-text">{word}…</span>
            </div>
          </div>
        </div>
      </article>
    );
  }

  function InlineLoadingPlaceholder() {
    const [word, setWord] = useState(() => getRandomWord());

    useEffect(() => {
      let prev = word;
      const interval = window.setInterval(() => {
        const next = getRandomWord(prev);
        prev = next;
        setWord(next);
      }, 2000);
      return () => window.clearInterval(interval);
    }, []);

    return (
      <div className="loading-placeholder-inner loading-placeholder-inline">
        <svg className="pl" viewBox="0 0 128 128" width="128" height="128" xmlns="http://www.w3.org/2000/svg">
          <circle className="pl__ring pl__ring--a" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--b" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--c" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--d" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
        </svg>
        <span className="loading-placeholder-text">{word}...</span>
      </div>
    );
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
      if (attachmentsForSend.some(isAudioVideoAttachment)) {
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
        selectedSkill?.name ?? null,
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
      setError(sendError instanceof ApiError ? sendError.message : "消息发送失败，请稍后重试。");
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
        throw new Error(`${tooLarge.name} 超过 20MB，请改用项目文件上传。`);
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
          source_label: activeWorkspace?.workspace_kind === "user" ? "个人工作台引用" : "项目资料引用",
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
        throw new Error(`${tooLarge.fileName} 超过 20MB，请改用项目文件上传。`);
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

  async function handleSavePendingPrivateAttachmentsToWorkspace() {
    if (!activeWorkspaceId) {
      setError("请先进入一个项目工作区，再保存到项目资料。");
      return;
    }
    const attachments = pendingAttachments.filter(
      (attachment) => isLocalPrivatePendingAttachment(attachment) && attachment.file,
    );
    if (!attachments.length) return;
    const confirmed = window.confirm(
      `将 ${attachments.length} 个本机选择文件复制到项目的 99-未归档文件。原文件不会移动或同步。是否继续？`,
    );
    if (!confirmed) return;
    setError(null);
    setIsUploadingAttachments(true);
    try {
      await uploadWorkspaceFiles(
        apiOptions,
        activeWorkspaceId,
        "99-未归档文件",
        attachments.map((attachment) => attachment.file).filter((file): file is File => Boolean(file)),
      );
      setUtilityPanel("workspace");
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "保存到项目资料失败。");
    } finally {
      setIsUploadingAttachments(false);
    }
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

  function renderEmptyState(isSplitPane: boolean) {
    if (isSplitPane) {
      return (
        <div className="empty-chat empty-chat-compact">
          <span className="empty-chat-mark">R</span>
          <h2>选择一个对话</h2>
          <p>先点击这个区域，再从左侧会话列表选择要放进来的对话。</p>
        </div>
      );
    }
    if (mode === "agent") {
      return (
        <div className={`empty-agent ${sideBySideOpen ? "is-split-mode" : ""}`}>
          <div className="empty-agent-copy">
            <span className="empty-chat-mark">R</span>
            <h2>{activeWorkspace ? `在「${activeWorkspace.name}」开始 Agent` : "选择项目后开始 Agent"}</h2>
            <p>直接说明你要整理、核对或生成的业务结果。</p>
          </div>
        </div>
      );
    }
    return (
      <div className="empty-chat">
        <span className="empty-chat-mark">R</span>
        <h2>{activeWorkspace ? `在「${activeWorkspace.name}」开始聊天` : "从一个问题开始"}</h2>
        <p>询问规范、整理资料，或把当前工作流交给 Project_R 梳理成可执行步骤。</p>
      </div>
    );
  }

  function renderMessageVersionBar(message: ChatMessage) {
    const versions = message.versions?.length ? message.versions : [];
    if (versions.length <= 1) return null;
    const activeIndex = Math.max(0, versions.findIndex((version) => version.active_version || version.id === message.id));
    const previous = versions[Math.max(0, activeIndex - 1)];
    const next = versions[Math.min(versions.length - 1, activeIndex + 1)];
    const isBusy = messageActionBusyId === message.id;
    return (
      <div className="message-version-bar">
        <button
          className="message-version-btn"
          disabled={activeIndex <= 0 || isBusy}
          onClick={() => previous ? void handleActivateVersion(message, previous) : undefined}
          type="button"
        >
          &lt;
        </button>
        <span>{activeIndex + 1} / {versions.length}</span>
        <button
          className="message-version-btn"
          disabled={activeIndex >= versions.length - 1 || isBusy}
          onClick={() => next ? void handleActivateVersion(message, next) : undefined}
          type="button"
        >
          &gt;
        </button>
      </div>
    );
  }

  function renderMessageCard(message: ChatMessage) {
    const isEditing = editingMessageId === message.id;
    const isBusy = messageActionBusyId === message.id;
    const hasMessageBubble = Boolean(message.content.trim()) || Boolean(message.isTyping) || Boolean(message.isRegenerating);
    return (
      <article className={`message-row message-row-${message.role} ${message.status === "failed" ? "message-row-failed" : ""}`} key={message.id}>
        {message.role === "assistant" ? (
          <span className="message-avatar assistant-avatar is-text">R</span>
        ) : (
          renderAvatar(currentUser?.avatar, currentUser?.nickname, 30, serverUrl)
        )}
        <div className="message-body">
          <div className="message-meta">
            <div className="message-name-line">
              <span className="message-role-label">{message.role === "user" ? currentUser?.nickname ?? "你" : APP_NAME}</span>
              {message.role === "assistant" && message.model ? <span className="model-badge">{message.model}</span> : null}
              <time className="message-time">{formatClockTime(message.created_at)}</time>
            </div>
          </div>
          {isEditing ? (
            <div className="message-edit-box">
              <textarea
                autoFocus
                onChange={(event) => setEditingDraft(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                    event.preventDefault();
                    void handleSubmitEditedMessage(message);
                  }
                  if (event.key === "Escape") {
                    setEditingMessageId(null);
                    setEditingDraft("");
                  }
                }}
                value={editingDraft}
              />
              <div className="message-edit-actions">
                <span>Ctrl + Enter 提交</span>
                <button className="btn-secondary" onClick={() => {
                  setEditingMessageId(null);
                  setEditingDraft("");
                }} type="button">取消</button>
                <button className="btn-primary" disabled={isBusy || !editingDraft.trim()} onClick={() => void handleSubmitEditedMessage(message)} type="button">
                  提交
                </button>
              </div>
            </div>
          ) : (
            <>
              <MessageAttachments attachments={message.attachments} apiOptions={apiOptions} />
              {hasMessageBubble ? (
                <div className="message-bubble">
                  {message.isRegenerating ? (
                    <InlineLoadingPlaceholder />
                  ) : (
                    renderMessageContent(message.content, message.sources ?? [], (preview) => {
                      setSourcePreview({ ...preview, sessionId: message.session_id });
                      setUtilityPanel("source");
                    })
                  )}
                  {message.isTyping && !message.isRegenerating ? <span className="typing-caret" /> : null}
                </div>
              ) : null}
            </>
          )}
          {renderMessageVersionBar(message)}
          {message.sources?.length ? (
            <div className="message-sources">
              <span className="message-sources-title">引用来源</span>
              {message.sources.map((source, index) => (
                <button
                  className="message-source-item"
                  key={`${source.file}-${index}`}
                  onClick={() => {
                    setSourcePreview({ index: index + 1, source, sessionId: message.session_id });
                    setUtilityPanel("source");
                  }}
                  type="button"
                >
                  <span className="message-source-index">[{index + 1}]</span>
                  <span className="message-source-path">{source.section_path || source.source_title}</span>
                  <span className="message-source-file">{source.file}</span>
                </button>
              ))}
            </div>
          ) : null}
          {message.role === "assistant" ? renderContextTraceCard(message.context_trace, {
            gbrainThinkReviewBusy: messageActionBusyId === message.id,
            onSubmitGBrainThinkReview: message.context_trace?.gbrain_think
              ? () => void handleSubmitGBrainThinkReview(message)
              : undefined,
          }) : null}
          {message.generated_file ? (
            renderGeneratedFileCard(
              message.generated_file,
              (file) => void downloadGeneratedFile(serverUrl, token, file),
            )
          ) : null}
          {message.agent_run ? renderAgentRunCard(message.agent_run) : null}
          {message.skill_run ? renderSkillRunCard(message.skill_run, {
            showGeneratedFile: !message.generated_file,
            onDownloadGeneratedFile: (file) => void downloadGeneratedFile(serverUrl, token, file),
          }) : null}
          {message.agent_suggestion ? (
            <div className="message-agent-suggestion">
              <div className="message-agent-suggestion-copy">
                <strong>建议切换到 Agent</strong>
                <span>{message.agent_suggestion.reason}</span>
              </div>
              <button
                className="message-agent-suggestion-btn"
                onClick={() => handleSwitchToAgent(message.id)}
                type="button"
              >
                <AgentIcon />
                <span>切换</span>
              </button>
            </div>
          ) : null}
          {message.role === "assistant" && message.feedback_rating ? (
            <div className="message-feedback-status">
              <span>已评分 {message.feedback_rating}/5</span>
              {message.feedback_comment ? <small>含意见</small> : null}
            </div>
          ) : null}
          <div className={`message-actions ${copiedMessageId === message.id ? "has-copy-success" : ""}`}>
            <button
              className={`message-action-btn ${copiedMessageId === message.id ? "is-copied" : ""}`}
              onClick={() => void handleCopyMessage(message)}
              title={copiedMessageId === message.id ? "已复制" : "复制"}
              type="button"
            >
              {copiedMessageId === message.id ? <span className="message-action-check">✓</span> : <CopyIcon />}
            </button>
            {message.role === "assistant" ? (
              <button
                className="message-action-btn"
                disabled={message.isOptimistic || isBusy}
                onClick={() => openRegenerateDialog(message)}
                title="重新生成"
                type="button"
              >
                <RefreshIcon />
              </button>
            ) : null}
            {message.role === "user" ? (
              <button
                className="message-action-btn"
                disabled={message.isOptimistic || isBusy}
                onClick={() => startEditingMessage(message)}
                title="编辑并开启新分支"
                type="button"
              >
                <EditIcon />
              </button>
            ) : null}
            {message.role === "assistant" ? (
              <button className="message-action-btn" onClick={() => handleSwitchToAgent(message.id)} title="切换到 Agent" type="button"><AgentIcon /></button>
            ) : null}
            {message.role === "assistant" ? (
              <button
                className={`message-action-btn ${message.feedback_rating ? "is-rated" : ""}`}
                disabled={message.isOptimistic || isBusy}
                onClick={() => openFeedbackDialog(message)}
                title="评分与意见"
                type="button"
              >
                <span className="message-action-star">★</span>
              </button>
            ) : null}
            <button
              className="message-action-btn"
              disabled={message.isOptimistic || isBusy}
              onClick={() => requestDeleteMessageContext(message)}
              title="删除当前问答"
              type="button"
            >
              <TrashIcon />
            </button>
          </div>
          {message.status === "failed" ? <p className="message-error">AI 服务暂时不可用</p> : null}
        </div>
      </article>
    );
  }

  function renderComposer(isActivePane: boolean, paneSessionId: number | null) {
    if (!isActivePane) {
      return <div className="composer-inactive-hint">点击此侧后继续输入</div>;
    }
    const sessionIsSending = paneSessionId ? Boolean(sendingSessions[paneSessionId]) : false;
    const localPrivateAttachments = pendingAttachments.filter(isLocalPrivatePendingAttachment);
    const unauthorizedLocalAttachmentCount = localPrivateAttachments.filter((attachment) => attachment.authorization_status !== "authorized").length;
    const hasUnauthorizedLocalAttachments = unauthorizedLocalAttachmentCount > 0;
    const hasLocalPrivateImages = localPrivateAttachments.some((attachment) => attachment.kind === "image");
    const canSendMessage = Boolean(draft.trim() || pendingAttachments.length) && !hasUnauthorizedLocalAttachments;
    const sendButtonTitle = sessionIsSending
      ? "停止生成 (Esc)"
      : hasUnauthorizedLocalAttachments
        ? "请先确认本机选择文件"
        : "发送";
    return (
      <div className="composer-wrap">
        <div className="composer" ref={composerRef}>
          {localPrivateAttachments.length ? (
            <div className={`composer-attachment-consent ${hasUnauthorizedLocalAttachments ? "is-pending" : "is-authorized"}`}>
              <div className="composer-attachment-consent-copy">
                  <strong>本机选择文件</strong>
                <span>
                  {hasUnauthorizedLocalAttachments
                    ? `${unauthorizedLocalAttachmentCount} 个文件来自本机选择，发送前需确认。Chat 模式文本默认只发送摘录；Agent 模式会把选中文件作为后端临时文件处理。${hasLocalPrivateImages ? " 图片确认后会上传给后端模型链路用于多模态理解。" : ""}`
                    : "已确认本次发送授权；这些文件不会自动进入项目资料或公司知识库。"}
                </span>
              </div>
              <button
                disabled={!hasUnauthorizedLocalAttachments}
                onClick={authorizeLocalPrivateAttachments}
                type="button"
              >
                {hasUnauthorizedLocalAttachments ? "确认本次发送" : "已确认"}
              </button>
            </div>
          ) : null}
          {pendingAttachments.length ? (
            <div className="composer-attachments">
              {pendingAttachments.map((attachment) => (
                <div
                  className={`composer-attachment-chip is-${attachment.kind} is-${attachment.source_scope} ${attachment.authorization_status === "authorized" ? "is-authorized" : ""}`}
                  key={pendingAttachmentKey(attachment)}
                  title={attachment.original_name}
                >
                  <span className="composer-attachment-badge">{attachment.input_source === "workspace_reference" ? "引用" : "附件"}</span>
                  {attachment.previewUrl ? (
                    <img alt="" className="composer-attachment-thumb" src={attachment.previewUrl} />
                  ) : (
                    <span className="composer-attachment-kind">
                      {attachment.kind === "pdf" ? "PDF" : attachment.kind === "text" ? "TXT" : <PaperclipIcon />}
                    </span>
                  )}
                  <span className="composer-attachment-name">{attachment.original_name}</span>
                  <small className="composer-attachment-meta">
                    {attachmentSourceLabel(attachment)} · {pendingAttachmentStatusLabel(attachment)} · {pendingAttachmentSendFormLabel(attachment, mode)} · {pendingAttachmentTargetLabel(mode)} · {formatAttachmentSize(attachment.size)}
                  </small>
                  {attachment.preprocess?.summary ? (
                    <em>{attachment.preprocess.summary}</em>
                  ) : null}
                  <button
                    aria-label={`移除附件：${attachment.original_name}`}
                    className="composer-attachment-remove"
                    onClick={() => void handleRemovePendingAttachment(attachment)}
                    title="移除附件"
                    type="button"
                  >
                    <XmarkIcon />
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          {isUploadingAttachments ? <div className="composer-uploading">附件处理中...</div> : null}
          {(!selectedPromptIsDefault || selectedSkill || selectedBuiltinCommand) ? (
            <div className="composer-context-row">
              {!selectedPromptIsDefault ? (
                <button
                  className="composer-context-chip composer-context-chip-prompt"
                  onClick={clearPromptSelection}
                  title="移除提示词"
                  type="button"
                >
                  <span className="composer-context-chip-icon"><PromptIcon /></span>
                  <strong>{selectedPrompt.name}</strong>
                  <small>提示词</small>
                </button>
              ) : null}
              {selectedBuiltinCommand ? (
                <button
                  className="composer-context-chip composer-context-chip-command"
                  onClick={() => {
                    setSelectedBuiltinCommand(null);
                    textareaRef.current?.focus();
                  }}
                  title="移除内置命令"
                  type="button"
                >
                  <span className="composer-context-chip-icon">/</span>
                  <strong>{selectedBuiltinCommand.displayName}</strong>
                  <small>内置命令</small>
                </button>
              ) : null}
              {selectedSkill ? (
                <button
                  className="composer-context-chip composer-context-chip-skill"
                  onClick={() => {
                    setSelectedSkill(null);
                    textareaRef.current?.focus();
                  }}
                  title="移除 Skill"
                  type="button"
                >
                  <span className="composer-context-chip-icon">/</span>
                  <strong>{selectedSkill.display_name}</strong>
                  <small>{getSkillScopeLabel(selectedSkill)}</small>
                </button>
              ) : null}
            </div>
          ) : null}
          {skillPanelVisible ? (
            <div className="skill-candidate-panel" role="listbox">
              <div className="skill-candidate-panel-header">
                <span>选择指令或 Skill</span>
                <kbd>/</kbd>
              </div>
              {slashCandidates.length > 0 ? (
                slashCandidates.map((candidate, index) => {
                  const isCommand = candidate.kind === "command";
                  const label = isCommand ? candidate.command.displayName : candidate.skill.display_name;
                  const description = isCommand ? candidate.command.description : candidate.skill.description;
                  const scope = isCommand ? candidate.command.scope : getSkillScopeLabel(candidate.skill);
                  const key = isCommand ? `command-${candidate.command.name}` : `skill-${candidate.skill.name}`;
                  return (
                  <button
                    key={key}
                    className={`skill-candidate-item ${index === skillPanelIndex ? "is-active" : ""}`}
                    onClick={() => insertSlashCandidate(candidate)}
                    onMouseEnter={() => setSkillPanelIndex(index)}
                    role="option"
                    type="button"
                  >
                    <span className="skill-candidate-icon">{isCommand ? "/" : "◆"}</span>
                    <span className="skill-candidate-copy">
                      <span className="skill-candidate-title">
                        <strong>{label}</strong>
                        <span>{description}</span>
                      </span>
                    </span>
                    <span className="skill-candidate-scope">{scope}</span>
                  </button>
                  );
                })
              ) : (
                <div className="skill-candidate-empty">没有匹配的指令或 Skill</div>
              )}
            </div>
          ) : null}
          <textarea
            onChange={(event) => {
              const value = event.target.value;
              const caret = event.target.selectionStart ?? value.length;
              setDraft(value);
              clearSelectedSkillIfMissing(value);
              syncSlashCommand(value, caret);
            }}
            onClick={(event) => syncSlashCommand(event.currentTarget.value, event.currentTarget.selectionStart ?? event.currentTarget.value.length)}
            onKeyDown={handleKeyDown}
            onPaste={handleComposerPaste}
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            ref={textareaRef}
            rows={1}
            value={draft}
          />
          <div className="composer-toolbar">
            <div className="composer-left-tools">
              <input
                className="hidden-file-input"
                multiple
                onChange={(event) => void handleSelectAttachmentFiles(event.target.files)}
                ref={fileInputRef}
                type="file"
              />
                <button
                  className="composer-tool-icon"
                  data-tooltip={isUploadingAttachments ? "附件处理中" : "添加会话临时附件"}
                  disabled={isUploadingAttachments}
                  onClick={() => fileInputRef.current?.click()}
                title="添加会话临时附件"
                type="button"
                >
                  <PaperclipIcon />
                </button>
                <button
                  className="composer-tool-icon"
                  data-tooltip={isUploadingAttachments ? "附件处理中" : "从本机选择文件"}
                  disabled={isUploadingAttachments}
                  onClick={() => void handleChoosePrivateWorkspaceFiles()}
                  title="从本机选择文件"
                  type="button"
                >
                  <WorkspaceIcon />
                </button>
              <div className="composer-config-group" aria-label="模型配置">
                <div className="composer-model-select" ref={modelSelectRef}>
                  <button
                    aria-label={`选择模型：${selectedModelOption?.label ?? (modelsLoading ? "加载模型" : "选择模型")}`}
                    aria-expanded={modelMenuOpen}
                    className="composer-model-button"
                    data-tooltip="切换模型"
                    onClick={() => setModelMenuOpen((value) => !value)}
                    title="选择模型"
                    type="button"
                  >
                    <SettingsIcon />
                    <span className="composer-model-label">{selectedModelOption?.label ?? (modelsLoading ? "加载模型" : "选择模型")}</span>
                    <ChevronDownIcon />
                  </button>
                  {modelMenuOpen ? (
                    <div className="model-dropdown-menu" role="listbox" aria-label="选择模型">
                      <div className="menu-group-title">已配置模型</div>
                      <div className="menu-items-list">
                        {modelOptions.map((option) => {
                          const selected = option.key === selectedModelOption?.key;
                          return (
                            <div
                              aria-selected={selected}
                              className={`menu-item ${selected ? "active" : ""}`}
                              key={option.key}
                              onClick={() => {
                                setSelectedModelKey(option.key);
                                setModelMenuOpen(false);
                                textareaRef.current?.focus();
                              }}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") {
                                  event.preventDefault();
                                  setSelectedModelKey(option.key);
                                  setModelMenuOpen(false);
                                  textareaRef.current?.focus();
                                }
                              }}
                              role="option"
                              tabIndex={0}
                            >
                              <div className="item-text-container">
                                <div className="item-title">{option.label}</div>
                                <div className="item-description">{option.description}</div>
                              </div>
                              {selected ? <div className="item-check-icon" aria-hidden="true">✓</div> : null}
                            </div>
                          );
                        })}
                        {modelsLoading ? (
                          <div className="model-menu-empty">读取模型配置...</div>
                        ) : null}
                        {!modelsLoading && modelOptions.length === 0 ? (
                          <div className="model-menu-empty">{modelConfigError || "暂无已配置模型"}</div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="composer-mode-toggles" aria-label="对话增强开关">
                  <button
                    aria-label={thinkingEnabled ? "关闭深度思考" : "开启深度思考"}
                    aria-pressed={thinkingEnabled}
                    className={`composer-mode-toggle is-thinking ${thinkingEnabled ? "is-active" : ""}`}
                    data-tooltip={thinkingEnabled ? "关闭深度思考" : "开启深度思考"}
                    onClick={() => setThinkingEnabled((value) => !value)}
                    title="深度思考"
                    type="button"
                  >
                    <BrainIcon />
                    <span className="composer-button-label">深度思考</span>
                  </button>
                  <button
                    aria-label={webSearchEnabled ? "关闭联网搜索" : "开启联网搜索"}
                    aria-pressed={webSearchEnabled}
                    className={`composer-mode-toggle is-search ${webSearchEnabled ? "is-active" : ""}`}
                    data-tooltip={webSearchEnabled ? "关闭联网搜索" : "开启联网搜索"}
                    onClick={toggleWebSearch}
                    title="联网搜索"
                    type="button"
                  >
                    <GlobeIcon />
                    <span className="composer-button-label">联网搜索</span>
                  </button>
                </div>
              </div>
            </div>
            <div className="composer-right-tools">
              <div className="composer-toolbox-group" aria-label="Agent 工具箱">
                <button
                  aria-label="提示词"
                  className={`composer-tool-button ${utilityPanel === "prompt" ? "is-active" : ""}`}
                  data-tooltip="提示词"
                  onClick={() => setUtilityPanel((value) => value === "prompt" ? null : "prompt")}
                  title={`提示词：${selectedPrompt.name}`}
                  type="button"
                >
                  <PromptIcon />
                  <span className="composer-button-label">提示词</span>
                </button>
                <button
                  aria-label="技能"
                  className={`composer-tool-button ${utilityPanel === "skills" ? "is-active" : ""}`}
                  data-tooltip="Skills"
                  onClick={() => setUtilityPanel((value) => value === "skills" ? null : "skills")}
                  title="Skills"
                  type="button"
                >
                  <AgentIcon />
                  <span className="composer-button-label">技能</span>
                </button>
              </div>
              <button
                className={`composer-send ${sessionIsSending ? "is-stopping" : ""}`}
                disabled={(!canSendMessage && !sessionIsSending) || isUploadingAttachments}
                onClick={() => sessionIsSending ? handleCancelSend(paneSessionId) : void handleSend()}
                title={sendButtonTitle}
                type="button"
              >
                {sessionIsSending ? <StopIcon /> : <SendIcon />}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  function renderConversationPane(pane: SplitPaneKey) {
    const paneSessionId = sideBySideOpen ? splitPaneSessionIds[pane] : activeSessionId;
    const paneSession = paneSessionId ? sessions.find((session) => session.id === paneSessionId) ?? null : null;
    const paneMessages = paneSessionId ? messagesBySession[paneSessionId] ?? [] : [];
    const isActivePane = !sideBySideOpen || activeSplitPane === pane;
    const isEmptySplitPane = sideBySideOpen && !paneSessionId;
    const isAttachmentDragOver = attachmentDragTargetPane === pane;

    return (
      <div
        className={`chat-conversation-pane ${isActivePane ? "is-active" : ""} ${isAttachmentDragOver ? "is-attachment-drag-over" : ""}`}
        onDragEnter={(event) => handleAttachmentDragEnter(event, pane)}
        onDragLeave={(event) => handleAttachmentDragLeave(event, pane)}
        onDragOver={(event) => handleAttachmentDragOver(event, pane)}
        onDrop={(event) => handleAttachmentDrop(event, pane, paneSessionId)}
        onClick={() => activateConversationPane(pane, paneSessionId)}
        key={pane}
      >
        {isAttachmentDragOver ? (
          <div className="attachment-drop-overlay">
            <div>
              <PaperclipIcon />
              <strong>释放以添加到当前对话</strong>
              <span>图片随本条消息发送，文本和 PDF 作为会话临时附件处理。</span>
            </div>
          </div>
        ) : null}
        <header className="chat-header">
          <div className="chat-header-title">
            <span className="chat-header-mode-icon">{mode === "agent" ? <AgentIcon /> : <ChatIcon />}</span>
            {paneSession && renameInput?.id === paneSession.id && renameInput.scope === "header" ? (
              <input
                autoFocus
                className="chat-title-input"
                onBlur={() => void commitRename()}
                onChange={(event) => setRenameInput({ id: paneSession.id, value: event.target.value, scope: "header" })}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void commitRename();
                  if (event.key === "Escape") setRenameInput(null);
                }}
                onClick={(event) => event.stopPropagation()}
                onMouseDown={(event) => event.stopPropagation()}
                ref={titleInputRef}
                value={renameInput.value}
              />
            ) : (
              <button
                className="chat-title-button"
                disabled={!paneSession}
                onMouseDown={(event) => {
                  if (!paneSession) return;
                  event.preventDefault();
                  event.stopPropagation();
                  handleRenameSession(paneSession.id, "header");
                }}
                onKeyDown={(event) => {
                  if (!paneSession) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    handleRenameSession(paneSession.id, "header");
                  }
                }}
                type="button"
              >
                <h1>{paneSession ? formatSessionDisplayTitle(paneSession.title) : (sideBySideOpen ? `${pane === "left" ? "左侧" : "右侧"}对话` : "新会话")}</h1>
                {paneSession ? <EditIcon /> : null}
              </button>
            )}
            {sideBySideOpen ? <span className="chat-workspace-chip">{isActivePane ? "当前输入区" : "点击激活"}</span> : null}
            {activeWorkspace && !sideBySideOpen ? <span className="chat-workspace-chip">{activeWorkspace.name}</span> : null}
          </div>
          <div className="chat-header-actions">
            <button
              className={`icon-button ${paneSession?.is_pinned ? "is-active" : ""}`}
              disabled={!paneSession}
              onClick={() => paneSession ? void handlePinSession(paneSession.id) : undefined}
              title={paneSession?.is_pinned ? "取消置顶" : "置顶"}
              type="button"
            >
              <PinIcon />
            </button>
            <button
              aria-pressed={sideBySideOpen}
              className={`icon-button ${sideBySideOpen ? "is-active" : ""}`}
              onClick={handleToggleSideBySide}
              title={sideBySideOpen ? "关闭对话并排" : "左右并排两个对话"}
              type="button"
            >
              <SplitIcon />
            </button>
            <button
              className={`icon-button ${utilityPanel === "workspace" ? "is-active" : ""}`}
              onClick={() => setUtilityPanel((value) => value === "workspace" ? null : "workspace")}
              title={utilityPanel === "workspace" ? (activeWorkspace?.workspace_kind === "user" ? "关闭个人文件" : "关闭项目文件") : (activeWorkspace?.workspace_kind === "user" ? "个人文件" : "项目文件")}
              type="button"
            >
              <WorkspaceIcon />
            </button>
            {paneSession ? (
              <button className="icon-button" onClick={() => setDeleteConfirmSessionId(paneSession.id)} title="删除当前会话" type="button">
                <TrashIcon />
              </button>
            ) : null}
          </div>
        </header>

        <div className="message-scroll" ref={isActivePane ? scrollRef : undefined}>
          {paneMessages.length === 0 ? renderEmptyState(isEmptySplitPane) : null}
          {paneMessages.map(renderMessageCard)}
          {paneSessionId && sendingSessions[paneSessionId] ? <LoadingPlaceholder /> : null}
        </div>

        {renderComposer(isActivePane, paneSessionId)}
      </div>
    );
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

  function renderUtilityResizeHandle(onMouseDown: (event: MouseEvent<HTMLDivElement>) => void, label: string) {
    return (
      <div
        aria-label={label}
        aria-orientation="vertical"
        className="utility-resize-handle"
        onMouseDown={onMouseDown}
        role="separator"
        title={label}
      />
    );
  }

  function renderSkillsSidePanel() {
    return (
      <aside
        className={`utility-side-pane auxiliary-side-pane ${auxiliaryPanelResizing ? "is-resizing" : ""}`}
        aria-label="Skills 面板"
        ref={auxiliaryPanelRef}
        style={{ flexBasis: auxiliaryPanelWidth, maxWidth: auxiliaryPanelMaxWidth(), width: auxiliaryPanelWidth }}
      >
        {renderUtilityResizeHandle(handleAuxiliaryPanelResizeStart, "调整 Skills 面板宽度")}
        <header className="utility-side-header">
          <div>
            <h2>Skills</h2>
            <p>选择后应用于本次发送</p>
          </div>
          <button
            className="prompt-panel-close"
            onClick={() => {
              setSourcePreview(null);
              setUtilityPanel(null);
            }}
            type="button"
          >
            ×
          </button>
        </header>
        <div className="utility-side-body">
          {skills.length > 0 ? skills.map((skill) => (
            <button className="skill-side-row" key={skill.name} onClick={() => handleSelectSkillFromSidePanel(skill)} type="button">
              <span className="skill-side-icon">/</span>
              <span className="skill-side-copy">
                <strong>{skill.display_name}</strong>
                <span>{skill.description}</span>
              </span>
              <small>{getSkillScopeLabel(skill)}</small>
            </button>
          )) : (
            <div className="prompt-empty">暂无可用 Skill</div>
          )}
        </div>
      </aside>
    );
  }

  function renderSourceSidePanel() {
    const preview = sourcePreview;
    return (
      <aside
        className={`utility-side-pane auxiliary-side-pane source-side-pane ${auxiliaryPanelResizing ? "is-resizing" : ""}`}
        aria-label="引用来源预览"
        ref={auxiliaryPanelRef}
        style={{ flexBasis: auxiliaryPanelWidth, maxWidth: auxiliaryPanelMaxWidth(), width: auxiliaryPanelWidth }}
      >
        {renderUtilityResizeHandle(handleAuxiliaryPanelResizeStart, "调整引用来源面板宽度")}
        <header className="utility-side-header">
          <div>
            <h2>引用来源</h2>
            <p>{preview ? `Source ${preview.index}` : "从正文来源标签打开"}</p>
          </div>
          <button
            className="prompt-panel-close"
            onClick={() => {
              setSourcePreview(null);
              setUtilityPanel(null);
            }}
            type="button"
          >
            ×
          </button>
        </header>
        {preview ? (
          <div className="source-preview-body">
            <span className="source-preview-index">[{preview.index}]</span>
            <h3>{preview.source.source_title || preview.source.file}</h3>
            <p className="source-preview-path">{preview.source.section_path || preview.source.file}</p>
            <p className="source-preview-file">{preview.source.file}</p>
            <div className="source-preview-markdown">
              {renderMessageContent(preview.source.content)}
            </div>
          </div>
        ) : (
          <div className="prompt-empty">点击 AI 回复中的来源标签后，会在这里预览片段。</div>
        )}
      </aside>
    );
  }

  function renderUtilityPanel() {
    if (utilityPanel === "workspace") {
      return (
        <aside
          className={`utility-side-pane workspace-files-side-pane ${workspacePanelResizing ? "is-resizing" : ""}`}
          aria-label={activeWorkspace?.workspace_kind === "user" ? "个人文件面板" : "项目文件常驻面板"}
          ref={workspacePanelRef}
          style={{ flexBasis: workspacePanelWidth, maxWidth: workspacePanelMaxWidth(), width: workspacePanelWidth }}
        >
          {renderUtilityResizeHandle(handleWorkspacePanelResizeStart, activeWorkspace?.workspace_kind === "user" ? "调整个人文件面板宽度" : "调整项目文件面板宽度")}
          <header className="utility-side-header">
            <div>
              <h2>{activeWorkspace?.workspace_kind === "user" ? "个人文件" : "项目文件"}</h2>
              <p>{activeWorkspace?.workspace_kind === "user" ? "用户自定义文件夹" : "当前工作区常驻视图"}</p>
            </div>
            <button className="prompt-panel-close" onClick={() => setUtilityPanel(null)} type="button">×</button>
          </header>
          <WorkspaceFilePanel
            apiOptions={apiOptions}
            onPreviewOpen={handleWorkspaceFilePreviewOpen}
            workspaceId={activeWorkspaceId}
            workspaceName={activeWorkspace?.name}
            workspaceKind={activeWorkspace?.workspace_kind}
            canIngestKnowledge={Boolean(activeWorkspace && activeWorkspace.workspace_kind !== "user" && activeWorkspace.can_rename)}
            defaultPath=""
            onReferenceFile={handleReferenceWorkspaceFile}
          />
        </aside>
      );
    }
    if (utilityPanel === "prompt") {
      return (
        <aside
          className={`utility-side-pane auxiliary-side-pane prompt-utility-side-pane ${auxiliaryPanelResizing ? "is-resizing" : ""}`}
          aria-label="提示词面板"
          ref={auxiliaryPanelRef}
          style={{ flexBasis: auxiliaryPanelWidth, maxWidth: auxiliaryPanelMaxWidth(), width: auxiliaryPanelWidth }}
        >
          {renderUtilityResizeHandle(handleAuxiliaryPanelResizeStart, "调整提示词面板宽度")}
          <PromptPanel
            embedded
            selectedPromptId={selectedPromptId}
            companyPrompts={companyPrompts}
            userPrompts={userPrompts}
            onSelect={handleSelectPrompt}
            onCreateUserPrompt={handleCreateUserPrompt}
            onDeleteUserPrompt={handleDeleteUserPrompt}
            onClose={() => setUtilityPanel(null)}
          />
        </aside>
      );
    }
    if (utilityPanel === "skills") {
      return renderSkillsSidePanel();
    }
    if (utilityPanel === "source") {
      return renderSourceSidePanel();
    }
    return null;
  }

  function renderNotificationPanel() {
    const tabs: Array<{ id: NotificationView; label: string; badge?: number }> = [
      { id: "all", label: "全部" },
      { id: "unread", label: "未读", badge: unreadNotificationCount },
      { id: "pending", label: "待处理", badge: pendingNotificationCount },
    ];

    return (
      <div className="notification-popover" ref={notificationPanelRef} role="dialog" aria-label="通知中心">
        <header className="notification-popover-header">
          <div>
            <h2>通知中心</h2>
            <p>{unreadNotificationCount > 0 ? `${unreadNotificationCount} 条未读` : "暂无未读通知"}</p>
          </div>
          <button
            className="notification-mark-read"
            disabled={unreadNotificationCount === 0}
            onClick={() => void handleMarkAllNotificationsRead()}
            type="button"
          >
            全部已读
          </button>
        </header>

        <div className="notification-tabs" role="tablist" aria-label="通知分类">
          {tabs.map((tab) => (
            <button
              aria-selected={notificationView === tab.id}
              className={`notification-tab ${notificationView === tab.id ? "is-active" : ""}`}
              key={tab.id}
              onClick={() => setNotificationView(tab.id)}
              role="tab"
              type="button"
            >
              <span>{tab.label}</span>
              {tab.badge ? <small>{tab.badge > 99 ? "99+" : tab.badge}</small> : null}
            </button>
          ))}
        </div>

        {availableUpdate ? (
          <button
            className="notification-update-entry"
            onClick={() => {
              setUpdateStep(downloadedUpdatePath ? "ready" : updateProgress?.status === "downloading" ? "downloading" : "available");
              setUpdateDialogOpen(true);
              setNotificationPanelOpen(false);
            }}
            type="button"
          >
            <span>
              <strong>新版本可用</strong>
              <small>Project_R v{availableUpdate.version}</small>
            </span>
            <span>{updateStep === "ready" ? "已就绪" : "查看"}</span>
          </button>
        ) : null}

        <div className="notification-list">
          {notificationsLoading ? <div className="notification-empty">正在读取通知...</div> : null}
          {!notificationsLoading && notifications.length === 0 ? <div className="notification-empty">暂无通知</div> : null}
          {!notificationsLoading
            ? notifications.map((notification) => {
                const isPending = notification.action_status === "pending";
                const canDismiss = isPending && notification.severity !== "critical";
                return (
                  <article
                    className={`notification-item is-${notification.category} is-${notification.severity} ${notification.is_read ? "" : "is-unread"} ${isPending ? "is-pending" : ""}`}
                    key={notification.id}
                  >
                    <div
                      className="notification-item-main"
                      onClick={() => void handleNotificationAction(notification)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          void handleNotificationAction(notification);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <div className="notification-item-meta">
                        <span className={`notification-category is-${notification.category}`}>
                          {notificationCategoryLabel(notification.category)}
                        </span>
                        {isPending ? <span className="notification-status">待处理</span> : null}
                        <time>{formatNotificationTime(notification.created_at)}</time>
                      </div>
                      <h3>{notification.title}</h3>
                      <p>{notification.content}</p>
                    </div>

                    {isPending ? (
                      <div className="notification-item-actions">
                        <button
                          className="notification-action-primary"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleNotificationActionStatus(notification, "done");
                          }}
                          type="button"
                        >
                          已处理
                        </button>
                        {canDismiss ? (
                          <button
                            className="notification-action-secondary"
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleNotificationActionStatus(notification, "dismissed");
                            }}
                            type="button"
                          >
                            忽略
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </article>
                );
              })
            : null}
        </div>
      </div>
    );
  }

  function renderUpdateDialog() {
    if (!updateDialogOpen || !availableUpdate) return null;
    const progressPercent = Math.max(0, Math.min(100, updateProgress?.percent ?? 0));
    const totalBytes = updateProgress?.totalBytes || availableUpdate.size_bytes;
    const receivedBytes = updateProgress?.receivedBytes ?? 0;
    const speed = formatUpdateSpeed(updateProgress?.bytesPerSecond ?? 0);
    const title = updateStep === "ready"
      ? "更新已就绪"
      : updateStep === "installing"
        ? "正在安装更新"
      : updateStep === "downloading"
        ? "正在下载更新"
        : updateStep === "failed"
          ? "更新失败"
          : availableUpdate.is_force_update
            ? "需要更新 Project_R"
            : "发现新版本";
    const description = updateStep === "ready"
      ? `v${availableUpdate.version} 已下载完成，重启应用即可完成更新。`
      : updateStep === "installing"
        ? "校验完成，正在静默安装更新。Project_R 将自动退出，安装器替换当前版本后会自动重启应用。"
      : updateStep === "downloading"
        ? `正在下载 v${availableUpdate.version}...`
        : updateStep === "failed"
          ? updateError || "自动更新失败，请联系管理员获取最新版安装包。"
          : `v${availableUpdate.version} 已发布，请确认后下载更新。`;

    return (
      <div className="update-dialog-backdrop" onClick={() => {
        if (!availableUpdate.is_force_update && updateStep !== "downloading" && updateStep !== "installing") setUpdateDialogOpen(false);
      }}>
        <section className="update-dialog" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
          <header className="update-dialog-header">
            <div>
              <h2>{title}</h2>
              <p>{description}</p>
            </div>
            {UPDATE_DOWNLOAD_DRY_RUN ? <span className="update-dry-run">dry-run</span> : null}
          </header>

          {updateStep === "available" || updateStep === "ready" ? (
            <div className="update-release-notes">
              {renderMessageContent(availableUpdate.release_notes || "本次更新未填写更新日志。")}
            </div>
          ) : null}

          {updateStep === "downloading" || updateStep === "installing" ? (
            <div className="update-download-panel">
              <div className="update-progress-track">
                <span style={{ width: `${progressPercent}%` }} />
              </div>
              <div className="update-progress-meta">
                <span>{updateStep === "installing" ? "安装中" : `${formatUpdateBytes(receivedBytes)} / ${formatUpdateBytes(totalBytes)}`}</span>
                <span>{updateStep === "installing" ? "安装完成后自动重启" : speed || "校验中"}</span>
              </div>
            </div>
          ) : null}

          {updateStep === "failed" ? (
            <div className="update-failure-message">自动更新失败，请联系管理员获取最新版安装包。</div>
          ) : null}

          <footer className="update-dialog-actions">
            {updateStep === "available" && availableUpdate.is_force_update ? (
              <button className="btn-secondary" onClick={() => void window.projectR?.window?.close()} type="button">退出软件</button>
            ) : null}
            {updateStep === "available" && !availableUpdate.is_force_update ? (
              <button className="btn-secondary" onClick={() => setUpdateDialogOpen(false)} type="button">稍后</button>
            ) : null}
            {updateStep === "available" ? (
              <button className="btn-primary" onClick={() => void startClientUpdateDownload()} type="button">下载并安装</button>
            ) : null}
            {updateStep === "failed" && availableUpdate.is_force_update ? (
              <button className="btn-primary" onClick={() => void window.projectR?.window?.close()} type="button">退出软件</button>
            ) : null}
            {updateStep === "failed" && !availableUpdate.is_force_update ? (
              <button className="btn-primary" onClick={() => setUpdateDialogOpen(false)} type="button">知道了</button>
            ) : null}
          </footer>
        </section>
      </div>
    );
  }

  const activeTab = tabs.find((item) => item.id === activeTabId);

  return (
    <div className="shell">
      <aside
        className={`chat-sidebar ${sidebarResizing ? "is-resizing" : ""}`}
        ref={sidebarRef}
        style={{ width: sidebarWidth }}
      >
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <span className="sidebar-brand-mark">R</span>
            <span className="sidebar-brand-name">{APP_NAME}</span>
          </div>

          <div className="mode-switch" data-active={mode} aria-label="模式切换">
            <span className="mode-switch-indicator" aria-hidden="true" />
            <button className={`mode-tab ${mode === "agent" ? "is-active" : ""}`} onClick={() => setMode("agent")} title="Agent" type="button">
              <AgentIcon />
              <span>Agent</span>
            </button>
            <button className={`mode-tab ${mode === "chat" ? "is-active" : ""}`} onClick={() => setMode("chat")} title="Chat" type="button">
              <ChatIcon />
              <span>Chat</span>
            </button>
          </div>

          <WorkspaceSelector
            apiOptions={apiOptions}
            canCreateProject={currentUser?.role === "admin"}
            onWorkspaceChanged={handleWorkspaceChanged}
          />

          <div className="sidebar-command-row">
            <button className="new-chat-button" onClick={handleCreateSession} type="button">
              <PlusIcon />
              <span>新建对话</span>
            </button>
            <button className="sidebar-search-button" onClick={() => setShowSearch(true)} title="搜索对话" type="button">
              <SearchIcon />
            </button>
          </div>
        </div>

        <div className="session-list" aria-label="会话列表">
          {isLoading && sessions.length === 0 ? <p className="sidebar-note">正在加载会话...</p> : null}
          {!isLoading && sessions.length === 0 ? <p className="sidebar-note">当前项目暂无会话。</p> : null}

          {sessionGroups.map((group) => (
            <div key={group.key}>
              {group.label ? <p className="session-group-label">{group.label}</p> : null}
              {group.items.map((session) => (
                <div
                  className={`session-item ${session.id === activeSessionId ? "is-active" : ""} ${sideBySideOpen && session.id === splitPaneSessionIds.left ? "is-in-left-pane" : ""} ${sideBySideOpen && session.id === splitPaneSessionIds.right ? "is-in-right-pane" : ""}`}
                  key={session.id}
                  onClick={(event) => selectSession(session, event.ctrlKey)}
                  onAuxClick={(event) => {
                    if (event.button === 1) selectSession(session, true);
                  }}
                  onContextMenu={(event) => openSessionMenu(event, session)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      selectSession(session);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  {renameInput?.id === session.id && renameInput.scope === "sidebar" ? (
                    <input
                      autoFocus
                      className="session-rename-input"
                      onBlur={() => void commitRename()}
                      onChange={(event) => setRenameInput({ ...renameInput, value: event.target.value })}
                      onClick={(event) => event.stopPropagation()}
                      onMouseDown={(event) => event.stopPropagation()}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void commitRename();
                        if (event.key === "Escape") setRenameInput(null);
                      }}
                      ref={sidebarRenameInputRef}
                      value={renameInput.value}
                    />
                  ) : (
                    <span className="session-title">
                      {session.is_pinned ? <span className="session-pin-badge"><PinIcon />置顶</span> : null}
                      <span>{formatSessionDisplayTitle(session.title)}</span>
                    </span>
                  )}
                  <span className="session-time">{formatSidebarTime(session.updated_at)}</span>
                  <button
                    className="session-more"
                    onClick={(event) => {
                      event.stopPropagation();
                      openSessionMenu(event, session);
                    }}
                    title="会话操作"
                    type="button"
                  >
                    <MoreIcon />
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="sidebar-user">
          <span className={`sidebar-user-avatar ${!resolveAvatarUrl(serverUrl, currentUser?.avatar) && !currentUser?.avatar ? "is-text" : ""}`}>
            {resolveAvatarUrl(serverUrl, currentUser?.avatar) ? (
              <img src={resolveAvatarUrl(serverUrl, currentUser?.avatar)} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            ) : (
              currentUser?.avatar || getInitials(currentUser?.nickname)
            )}
          </span>
          <div className="sidebar-user-info">
            <span className="sidebar-user-name">{currentUser?.nickname ?? "未登录"}</span>
            <span className="sidebar-user-role">{currentUser?.role === "admin" ? "管理员" : "员工"}</span>
          </div>
          <div className="sidebar-user-actions">
            <button
              aria-expanded={notificationPanelOpen}
              className={`icon-button notification-button ${unreadNotificationCount > 0 ? "has-unread" : ""}`}
              onClick={() => setNotificationPanelOpen((value) => !value)}
              ref={notificationButtonRef}
              title="通知中心"
              type="button"
            >
              <BellIcon />
              {unreadNotificationCount > 0 ? (
                <span className="notification-badge">{unreadNotificationCount > 99 ? "99+" : unreadNotificationCount}</span>
              ) : null}
            </button>
            <button className="icon-button" onClick={() => { setSettingsInitialAdminTab(null); setShowSettings(true); }} title="设置" type="button"><SettingsIcon /></button>
            <button className="icon-button" onClick={handleLogout} title="登出" type="button"><LogoutIcon /></button>
          </div>
        </div>
        <div
          aria-label="调整功能栏宽度"
          aria-orientation="vertical"
          className="sidebar-resize-handle"
          onMouseDown={handleSidebarResizeStart}
          role="separator"
          title="拖动调整功能栏宽度"
        />
      </aside>

      {notificationPanelOpen ? renderNotificationPanel() : null}

      <section className="chat-main">
        <TabBar
          tabs={tabs}
          activeTabId={activeTabId}
          scratchOpen={showScratchPad}
          onSelectTab={handleSelectTab}
          onCloseTab={handleCloseTab}
          onAddChat={handleCreateSession}
          onOpenScratch={handleOpenScratch}
        />
        {error ? <p className="chat-error">{error}</p> : null}
        {actionNotice ? <p className="chat-notice">{actionNotice}</p> : null}
        {deletedMessageUndo ? (
          <div className="notification-toast message-undo-toast">
            <div>
              <div className="notification-toast-title">已删除当前问答</div>
              <div className="notification-toast-body">上下文已同步清理，可在数秒内撤回。</div>
            </div>
            <button onClick={() => void handleUndoDeleteMessages()} type="button">撤回删除</button>
          </div>
        ) : null}
        {notificationToast ? (
          <div
            className={`notification-toast notification-event-toast is-${notificationToast.severity}`}
            onClick={() => void handleNotificationAction(notificationToast)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                void handleNotificationAction(notificationToast);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <div className="notification-toast-title">{notificationToast.title}</div>
            <div className="notification-toast-body">{notificationToast.content}</div>
          </div>
        ) : null}

        {showScratchPad ? (
          <div className="scratch-pad-workspace">
            <ScratchPad
              workspaceId={activeWorkspaceId}
              workspaceName={activeWorkspace?.name}
              userId={currentUser?.user_id}
              onClose={() => setShowScratchPad(false)}
            />
          </div>
        ) : (
          <div className={`chat-workbench ${sideBySideOpen ? "is-split" : ""} ${utilityPanel ? "has-files-pane" : ""}`}>
            {renderConversationPane("left")}
            {sideBySideOpen ? renderConversationPane("right") : null}
            {renderUtilityPanel()}
          </div>
        )}
      </section>

      {useContextMenu(contextMenu, setContextMenu)}
      {moveSessionId !== null ? (
        <div className="confirm-overlay" onClick={() => setMoveSessionId(null)}>
          <div className="move-project-card" onClick={(event) => event.stopPropagation()}>
            <header className="move-project-header">
              <div>
                <h3>迁移项目</h3>
                <p>选择一个目标项目，当前会话会从项目列表中移出。</p>
              </div>
              <button className="prompt-panel-close" onClick={() => setMoveSessionId(null)} type="button">×</button>
            </header>
            <div className="move-project-list">
              {workspaces
                .filter((workspace) => workspace.id !== sessions.find((session) => session.id === moveSessionId)?.workspace_id)
                .map((workspace) => (
                  <button
                    className="move-project-item"
                    key={workspace.id}
                    onClick={() => void handleMoveSession(moveSessionId, workspace.id)}
                    type="button"
                  >
                    <WorkspaceIcon />
                    <span>{workspace.name}</span>
                    <small>{workspace.member_count} 人</small>
                  </button>
                ))}
            </div>
          </div>
        </div>
      ) : null}
      {showSearch ? (
        <SearchDialog
          sessions={sessions}
          results={searchTerm.trim() ? searchResults : undefined}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          onSelect={(id) => {
            const session = [...sessions, ...searchResults].find((item) => item.id === id);
            if (session) selectSession(session);
          }}
          onClose={() => setShowSearch(false)}
        />
      ) : null}

      {regenerateTarget !== null ? (
        <div className="confirm-overlay" onClick={() => setRegenerateTarget(null)}>
          <div className="confirm-card message-operation-card" onClick={(event) => event.stopPropagation()}>
            <h3>重新生成回答</h3>
            <p>保留当前回答为历史版本，并使用所选模型生成一个新版本。当前回答不会被覆盖。</p>
            <label className="message-operation-field">
              <span>使用模型</span>
              <select
                onChange={(event) => setRegenerateModelKey(event.target.value)}
                value={regenerateModelOption?.key ?? ""}
              >
                {modelOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setRegenerateTarget(null)} type="button">取消</button>
              <button
                className="btn-primary"
                disabled={!regenerateModelOption || messageActionBusyId === regenerateTarget.id}
                onClick={() => void handleRegenerateMessage(regenerateTarget)}
                type="button"
              >
                生成新版本
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {feedbackTarget !== null ? (
        <div className="confirm-overlay" onClick={() => setFeedbackTarget(null)}>
          <div className="confirm-card message-operation-card" onClick={(event) => event.stopPropagation()}>
            <h3>回答评分</h3>
            <p>评分和意见会保存到后端反馈目录；低分且带知识库引用的回答会进入管理员知识纠错审核。</p>
            <div className="message-rating-row" role="radiogroup" aria-label="回答评分">
              {[1, 2, 3, 4, 5].map((rating) => (
                <button
                  className={`message-rating-btn ${feedbackRating === rating ? "is-active" : ""}`}
                  key={rating}
                  onClick={() => setFeedbackRating(rating)}
                  type="button"
                >
                  {rating}
                </button>
              ))}
            </div>
            <label className="message-operation-field">
              <span>补充意见</span>
              <textarea
                onChange={(event) => setFeedbackComment(event.target.value)}
                placeholder="例如：回答遗漏了 AS2047 条款，或格式更适合项目周报。"
                value={feedbackComment}
              />
            </label>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setFeedbackTarget(null)} type="button">取消</button>
              <button
                className="btn-primary"
                disabled={feedbackRating < 1 || messageActionBusyId === feedbackTarget.id}
                onClick={() => void handleSubmitFeedback()}
                type="button"
              >
                保存评分
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteMessageTarget !== null ? (
        <div className="confirm-overlay" onClick={() => setDeleteMessageTarget(null)}>
          <div className="confirm-card" onClick={(event) => event.stopPropagation()}>
            <h3>删除消息上下文</h3>
            <p>确定删除此条消息对应的问答吗？这些内容会从当前对话视图和后续 AI 上下文中排除，并可在数秒内撤回。</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteMessageTarget(null)} type="button">取消</button>
              <button
                className="btn-danger"
                onClick={() => {
                  void handleDeleteMessageContext(deleteMessageTarget);
                  setDeleteMessageTarget(null);
                }}
                type="button"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteLastMessageTarget !== null ? (
        <div className="confirm-overlay" onClick={() => setDeleteLastMessageTarget(null)}>
          <div className="confirm-card" onClick={(event) => event.stopPropagation()}>
            <h3>删除最后一条消息</h3>
            <p>这是该对话中的最后一组消息。删除后整个对话会被删除，且无法恢复。</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteLastMessageTarget(null)} type="button">取消</button>
              <button
                className="btn-danger"
                onClick={() => {
                  void handleDeleteSession(deleteLastMessageTarget.session_id);
                  setDeleteLastMessageTarget(null);
                }}
                type="button"
              >
                删除对话
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteConfirmSessionId !== null ? (
        <div className="confirm-overlay" onClick={() => setDeleteConfirmSessionId(null)}>
          <div className="confirm-card" onClick={(event) => event.stopPropagation()}>
            <h3>确认删除</h3>
            <p>确定删除此对话吗？此操作不可恢复。</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirmSessionId(null)} type="button">取消</button>
              <button
                className="btn-danger"
                onClick={() => {
                  void handleDeleteSession(deleteConfirmSessionId);
                  setDeleteConfirmSessionId(null);
                }}
                type="button"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {renderUpdateDialog()}
      <SettingsModal
        initialAdminTab={settingsInitialAdminTab ?? undefined}
        initialSection={settingsInitialAdminTab ? "admin" : undefined}
        isOpen={showSettings}
        onArchiveRestored={handleArchiveRestored}
        onClose={() => {
          setShowSettings(false);
          setSettingsInitialAdminTab(null);
        }}
      />
    </div>
  );
}
