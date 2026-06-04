import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  applyGBrainEntityMergeCandidateAction,
  cancelGBrainJob,
  createAdminUser,
  deleteAdminUser,
  getGBrainEntityMergeCandidates,
  getGBrainEntityMergeCandidatePreview,
  getGBrainGraph,
  getGBrainMaintenance,
  pollGBrainCitationFixerJobs,
  pollGBrainDreamCycleJobs,
  listAdminTemplates,
  listAdminGroupCandidates,
  listAdminUserCandidates,
  listAdminUsers,
  listAuditLogs,
  listKnowledgeReviews,
  getKnowledgeQualityReport,
  getKnowledgeStatus,
  refreshKnowledge,
  restartGBrainDreamCycleWorker,
  restartGBrainService,
  rollbackGBrainCitationFixerJob,
  retryGBrainJob,
  resetAdminUserPassword,
  reviewKnowledge,
  runKnowledgeRegression,
  runGBrainContradictionProbe,
  runGBrainDreamCycle,
  runGBrainMaintenanceCheck,
  startGBrainService,
  submitGBrainCitationFixer,
  submitGBrainJob,
  submitKnowledgeReviewCitationFixer,
  tickGBrainDreamCycle,
  tickGBrainContradictionProbe,
  updateGBrainContradictionProbe,
  updateGBrainDreamCycle,
  updateAdminUser,
} from "../api/admin";
import { updateCurrentUser, uploadCurrentUserAvatar } from "../api/auth";
import { ApiError, apiRequest } from "../api/client";
import { listArchivedChatSessions, restoreChatSession } from "../api/chat";
import { listCompanyPrompts } from "../api/prompts";
import { listSkills } from "../api/skills";
import { listClientUpdateReleases, uploadClientUpdateRelease } from "../api/updates";
import { parseApiDate } from "../utils/time";
import type {
  AdminGroupCandidateResponse,
  AdminTemplateStatusResponse,
  AdminUserCandidateResponse,
  AdminUserResponse,
  AuditLogResponse,
  ChatSessionResponse,
  ClientUpdateInfo,
  CompanyPromptResponse,
  GBrainEntityMergeCandidate,
  GBrainEntityMergeCandidatesResponse,
  GBrainEntityMergePreviewResponse,
  GBrainMaintenanceResponse,
  GBrainGraphResponse,
  GBrainToolResponse,
  HealthResponse,
  KnowledgeReviewResponse,
  KnowledgeStatusResponse,
  SkillResponse,
} from "../api/types";
import { authTokenAtom, clearAuthAtom, currentUserAtom, refreshCurrentUserAtom } from "../atoms/auth-atoms";
import { serverUrlAtom, setServerUrlAtom } from "../atoms/server-atoms";
import { PROJECT_R_BUILTIN_PROMPT } from "../constants/prompts";
import {
  AgentIcon,
  ArchiveIcon,
  BrainIcon,
  CameraIcon,
  ChevronDownIcon,
  CopyIcon,
  EditIcon,
  MoreIcon,
  NoteIcon,
  PlusIcon,
  PromptIcon,
  RefreshIcon,
  SearchIcon,
  SendIcon,
  SettingsIcon,
  ShieldIcon,
  WorkspaceIcon,
  XmarkIcon,
} from "./LineIcons";

const CUSTOMER_INTELLIGENCE_SOURCE_ID = "customer-reference";

type ConnectionState = "idle" | "checking" | "ok" | "error";
type SettingsSection =
  | "general"
  | "server"
  | "prompts"
  | "archive"
  | "agent"
  | "remote"
  | "tutorial"
  | "shortcuts"
  | "admin";
type AdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type AdminUserRole = "admin" | "employee";
type AdminUserConfirmState =
  | { type: "role"; user: AdminUserResponse; nextRole: AdminUserRole }
  | { type: "status"; user: AdminUserResponse; nextActive: boolean }
  | { type: "delete"; user: AdminUserResponse };
type AdminPasswordDialogState = {
  user: AdminUserResponse;
  password: string;
  resultPassword: string | null;
  copied: boolean;
};
type AdminComboOption = {
  value: string;
  label: string;
  meta?: string;
  badge?: string;
  disabled?: boolean;
};
type PreferenceState = {
  completionSound: boolean;
  autoArchiveDays: string;
  floatingPinBar: boolean;
  theme: "system" | "light" | "dark";
  dingTalkWebhook: string;
  dingTalkToken: string;
  shortcuts: Record<string, string>;
};

const DEFAULT_SHORTCUTS: Record<string, string> = {
  newChat: "Ctrl + N",
  search: "Ctrl + K",
  settings: "Ctrl + ,",
  send: "Enter",
  newline: "Shift + Enter",
};

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const PREFS_KEY = "project-r:settings-preferences";

function readPreferences(): PreferenceState {
  try {
    return {
      completionSound: false,
      autoArchiveDays: "disabled",
      floatingPinBar: true,
      theme: "system",
      dingTalkWebhook: "",
      dingTalkToken: "",
      shortcuts: DEFAULT_SHORTCUTS,
      ...JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}"),
    };
  } catch {
    return {
      completionSound: false,
      autoArchiveDays: "disabled",
      floatingPinBar: true,
      theme: "system",
      dingTalkWebhook: "",
      dingTalkToken: "",
      shortcuts: DEFAULT_SHORTCUTS,
    };
  }
}

function applyTheme(theme: PreferenceState["theme"]) {
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  const resolved = theme === "system" ? (prefersDark ? "dark" : "light") : theme;
  document.documentElement.dataset.theme = resolved;
}

function formatDate(value: string | number) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parseApiDate(value));
}

function formatOptionalDate(value?: string | null) {
  if (!value) return "暂无记录";
  const date = parseApiDate(value);
  if (Number.isNaN(date.getTime())) return "暂无记录";
  return formatDate(value);
}

function resolveServerAssetUrl(serverUrl: string, value?: string | null) {
  if (!value) return "";
  if (value.startsWith("http") || value.startsWith("data:")) return value;
  if (value.startsWith("/")) return `${serverUrl.replace(/\/$/, "")}${value}`;
  return "";
}

function roleLabel(role: string) {
  return role === "admin" ? "管理员" : "员工";
}

function userDisplayName(user: AdminUserResponse) {
  return user.nickname?.trim() || user.username;
}

function isSystemAccount(user: AdminUserResponse | null | undefined) {
  return Boolean(user?.is_system_account || user?.username === "sysadmin");
}

function filterAdminComboOptions(options: AdminComboOption[], value: string, limit = 8) {
  const normalized = value.trim().toLowerCase();
  const filtered = normalized
    ? options.filter((option) => (
      option.label.toLowerCase().includes(normalized)
      || option.value.toLowerCase().includes(normalized)
      || (option.meta ?? "").toLowerCase().includes(normalized)
      || (option.badge ?? "").toLowerCase().includes(normalized)
    ))
    : options;
  return filtered.slice(0, limit);
}

function AdminComboInput({
  value,
  options,
  placeholder,
  disabled,
  icon,
  className = "",
  onChange,
  onSelect,
  onCommit,
}: {
  value: string;
  options: AdminComboOption[];
  placeholder: string;
  disabled?: boolean;
  icon?: ReactNode;
  className?: string;
  onChange: (value: string) => void;
  onSelect?: (value: string) => void;
  onCommit?: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const visibleOptions = filterAdminComboOptions(options, value);
  const hasMenu = open && !disabled && visibleOptions.length > 0;

  return (
    <div className={`admin-combo-input workspace-suggest-input ${className}`}>
      <label className={icon ? "has-icon" : ""}>
        {icon}
        <input
          disabled={disabled}
          placeholder={placeholder}
          value={value}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onCommit?.(value);
              setOpen(false);
            }
            if (event.key === "Escape") {
              setOpen(false);
            }
          }}
        />
      </label>
      {hasMenu ? (
        <div className="workspace-suggest-menu admin-combo-menu">
          {visibleOptions.map((option) => (
            <button
              disabled={option.disabled}
              key={`${option.value}-${option.badge ?? ""}`}
              onMouseDown={(event) => {
                event.preventDefault();
                onChange(option.value);
                onSelect?.(option.value);
                setOpen(false);
              }}
              type="button"
            >
              <span>
                <strong>{option.label}</strong>
                {option.meta ? <small>{option.meta}</small> : null}
              </span>
              {option.badge ? <em>{option.badge}</em> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function adminConfirmTitle(confirm: AdminUserConfirmState) {
  if (confirm.type === "role") return "确认修改角色";
  if (confirm.type === "delete") return "确认删除账号";
  return confirm.nextActive ? "确认启用账号" : "确认停用账号";
}

function adminConfirmText(confirm: AdminUserConfirmState) {
  if (confirm.type === "role") {
    return `确定要将 ${userDisplayName(confirm.user)} 的角色更改为 ${roleLabel(confirm.nextRole)} 吗？`;
  }
  if (confirm.type === "delete") {
    return `确定要删除 ${userDisplayName(confirm.user)} 吗？该账号将无法登录，调试数据会被清理，项目文件会转交给当前管理员。`;
  }
  return confirm.nextActive
    ? `确定要启用 ${userDisplayName(confirm.user)} 吗？该用户将恢复登录权限。`
    : `确定要停用 ${userDisplayName(confirm.user)} 吗？该用户将无法登录，但历史记录会保留。`;
}

function adminConfirmIsDanger(confirm: AdminUserConfirmState) {
  return confirm.type === "delete" || (confirm.type === "status" && !confirm.nextActive);
}

function generateTemporaryPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const bytes = new Uint32Array(12);
  if (window.crypto?.getRandomValues) {
    window.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = Math.floor(Math.random() * chars.length);
    }
  }
  const body = Array.from(bytes, (value) => chars[value % chars.length]).join("");
  return `Pr${body}!9`;
}

function statusLabel(value?: string | null) {
  if (!value) return "-";
  const labels: Record<string, string> = {
    ok: "正常",
    registered: "已注册",
    missing: "未注册",
    path_mismatch: "路径不一致",
    unreachable: "不可用",
    auth_required: "缺少 Token",
    disabled: "已禁用",
    oauth_required: "缺 OAuth",
    configured_unverified: "已配置未验收",
    ready: "可执行",
    warnings: "有警告",
    healthy: "健康",
    unhealthy: "异常",
  };
  return labels[value] ?? value;
}

function yesNo(value?: boolean | null) {
  if (value === true) return "是";
  if (value === false) return "否";
  return "-";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function recordText(record: Record<string, unknown> | null | undefined, key: string) {
  const value = record?.[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function recordNumber(record: Record<string, unknown> | null | undefined, key: string) {
  const value = record?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toolStatus(response?: GBrainToolResponse | null) {
  return statusLabel(typeof response?.status === "string" ? response.status : response?.ok ? "ok" : undefined);
}

function toolResultArray(response?: GBrainToolResponse | null, nestedKey?: string): Array<Record<string, unknown>> {
  const result = response?.result;
  if (Array.isArray(result)) {
    return result.map(asRecord).filter(Boolean) as Array<Record<string, unknown>>;
  }
  const record = asRecord(result);
  if (!record) return [];
  const nested = nestedKey ? record[nestedKey] : null;
  if (Array.isArray(nested)) {
    return nested.map(asRecord).filter(Boolean) as Array<Record<string, unknown>>;
  }
  return [];
}

function shortValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value).slice(0, 140);
  } catch {
    return String(value);
  }
}

const SECTION_LABELS: Record<SettingsSection, string> = {
  general: "通用设置",
  server: "服务器连接",
  prompts: "提示词管理",
  archive: "归档管理",
  agent: "Agent 配置",
  remote: "远程连接",
  tutorial: "软件教程",
  shortcuts: "快捷键管理",
  admin: "管理员后台",
};

export type SettingsModalProps = {
  isOpen: boolean;
  onClose: () => void;
  initialSection?: SettingsSection;
  initialAdminTab?: AdminTab;
  onArchiveRestored?: (session: ChatSessionResponse) => void | Promise<void>;
};

export function SettingsModal({ isOpen, onClose, initialSection, initialAdminTab, onArchiveRestored }: SettingsModalProps) {
  const [serverUrl] = useAtom(serverUrlAtom);
  const setServerUrl = useSetAtom(setServerUrlAtom);
  const token = useAtomValue(authTokenAtom);
  const currentUser = useAtomValue(currentUserAtom);
  const clearAuth = useSetAtom(clearAuthAtom);
  const refreshCurrentUser = useSetAtom(refreshCurrentUserAtom);
  const [draft, setDraft] = useState(serverUrl);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [activeSection, setActiveSection] = useState<SettingsSection>("general");
  const [preferences, setPreferences] = useState<PreferenceState>(readPreferences);
  const [profileDraft, setProfileDraft] = useState({
    nickname: currentUser?.nickname ?? "",
    avatar: currentUser?.avatar ?? "",
  });
  const [isEditingName, setIsEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [showAvatarPicker, setShowAvatarPicker] = useState(false);
  const [pickerPos, setPickerPos] = useState<{ top: number; left: number } | null>(null);
  const avatarRef = useRef<HTMLDivElement>(null);
  const avatarPickerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const updateFileInputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState("保存后会立即测试 /health。");
  const [archivedSessions, setArchivedSessions] = useState<ChatSessionResponse[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [restoringArchiveId, setRestoringArchiveId] = useState<number | null>(null);
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [companyPrompts, setCompanyPrompts] = useState<CompanyPromptResponse[]>([]);
  const [userPrompts, setUserPrompts] = useState<UserPromptRecord[]>([]);
  const [promptDraft, setPromptDraft] = useState({ id: "", name: "", content: "" });
  const [privateWorkspace, setPrivateWorkspace] = useState<PrivateWorkspaceConfig | null>(null);
  const [privateWorkspaceMessage, setPrivateWorkspaceMessage] = useState("");

  // Admin state
  const [adminUsers, setAdminUsers] = useState<AdminUserResponse[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [knowledgeReviews, setKnowledgeReviews] = useState<KnowledgeReviewResponse[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatusResponse | null>(null);
  const [gbrainMaintenance, setGBrainMaintenance] = useState<GBrainMaintenanceResponse | null>(null);
  const [gbrainGraph, setGBrainGraph] = useState<GBrainGraphResponse | null>(null);
  const [gbrainEntityMerge, setGBrainEntityMerge] = useState<GBrainEntityMergeCandidatesResponse | null>(null);
  const [gbrainEntityMergePreview, setGBrainEntityMergePreview] = useState<GBrainEntityMergePreviewResponse | null>(null);
  const [templates, setTemplates] = useState<AdminTemplateStatusResponse["items"]>([]);
  const [updateReleases, setUpdateReleases] = useState<ClientUpdateInfo[]>([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminMessage, setAdminMessage] = useState("");
  const [newUser, setNewUser] = useState({ username: "", nickname: "", password: "", role: "employee", work_group: "" });
  const [adminUserCandidates, setAdminUserCandidates] = useState<AdminUserCandidateResponse[]>([]);
  const [adminGroupCandidates, setAdminGroupCandidates] = useState<AdminGroupCandidateResponse[]>([]);
  const [userGroupDrafts, setUserGroupDrafts] = useState<Record<number, string>>({});
  const [auditFilter, setAuditFilter] = useState({ userId: "", dateFrom: "", dateTo: "" });
  const [citationFixerDraft, setCitationFixerDraft] = useState({
    pageSlug: "",
    reviewId: "",
    slugPrefixes: "",
    notes: "",
    maxTurns: "30",
  });
  const [gbrainGraphDraft, setGBrainGraphDraft] = useState({
    sourceId: CUSTOMER_INTELLIGENCE_SOURCE_ID,
    focus: "5Points",
    entityType: "",
  });
  const [gbrainDreamDraft, setGBrainDreamDraft] = useState({
    enabled: false,
    intervalHours: "168",
    targetScore: "90",
    sourceId: "company-wiki",
    jobNames: "autopilot-cycle",
  });
  const [gbrainContradictionDraft, setGBrainContradictionDraft] = useState({
    enabled: false,
    intervalHours: "168",
    sourceId: "company-wiki",
    queries: "书面化原则是什么\n项目邮件相关规则是什么\nVMU 标准作业流程是什么",
    topK: "5",
    budgetUsd: "1",
    judgeModel: "",
    timeoutSeconds: "600",
    resultLimit: "20",
  });
  const [updateDraft, setUpdateDraft] = useState({
    version: "",
    minimumSupportedVersion: "",
    platform: "win32",
    releaseNotes: "",
    isForceUpdate: false,
    isActive: true,
  });
  const [updateFile, setUpdateFile] = useState<File | null>(null);

  // Admin sub-tab state
  const [adminTab, setAdminTab] = useState<AdminTab>("overview");
  const [userSearch, setUserSearch] = useState("");
  const [userPage, setUserPage] = useState(1);
  const [userSort, setUserSort] = useState<{ field: "username" | "created_at"; dir: "asc" | "desc" }>({ field: "created_at", dir: "desc" });
  const [reviewSearch, setReviewSearch] = useState("");
  const [reviewPage, setReviewPage] = useState(1);
  const [templateSearch, setTemplateSearch] = useState("");
  const [auditSearch, setAuditSearch] = useState("");
  const [auditPage, setAuditPage] = useState(1);
  const [auditActionType, setAuditActionType] = useState("");
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUserResponse | null>(null);
  const [editUserDraft, setEditUserDraft] = useState({ nickname: "" });
  const [openUserMenuId, setOpenUserMenuId] = useState<number | null>(null);
  const [adminConfirm, setAdminConfirm] = useState<AdminUserConfirmState | null>(null);
  const [passwordDialog, setPasswordDialog] = useState<AdminPasswordDialogState | null>(null);

  const apiOptions = useMemo(
    () => ({ baseUrl: serverUrl, token, onUnauthorized: clearAuth }),
    [clearAuth, serverUrl, token],
  );
  const profileAvatarUrl = resolveServerAssetUrl(serverUrl, profileDraft.avatar);
  const profileLocked = currentUser?.username === "sysadmin";
  const adminUserSearchOptions = useMemo<AdminComboOption[]>(() => (
    adminUserCandidates.map((candidate) => ({
      value: candidate.username,
      label: candidate.nickname || candidate.username,
      meta: `${candidate.username}${candidate.work_group ? ` · ${candidate.work_group}` : ""}`,
      badge: candidate.is_system_account ? "固定" : candidate.is_active ? roleLabel(candidate.role) : "停用",
    }))
  ), [adminUserCandidates]);
  const adminGroupOptions = useMemo<AdminComboOption[]>(() => (
    adminGroupCandidates.map((candidate) => ({
      value: candidate.group_name,
      label: candidate.group_name,
      meta: `${candidate.user_count} 个用户`,
      badge: "组别",
    }))
  ), [adminGroupCandidates]);

  function syncGBrainDreamDraft(result: GBrainMaintenanceResponse | null) {
    const dream = result?.dream_cycle;
    if (!dream) return;
    setGBrainDreamDraft({
      enabled: Boolean(dream.enabled),
      intervalHours: String(dream.interval_hours ?? 168),
      targetScore: String(dream.target_score ?? 90),
      sourceId: dream.source_id || "company-wiki",
      jobNames: (dream.job_names ?? ["autopilot-cycle"]).join(","),
    });
  }

  function syncGBrainContradictionDraft(result: GBrainMaintenanceResponse | null) {
    const probe = result?.contradiction_probe;
    if (!probe) return;
    setGBrainContradictionDraft({
      enabled: Boolean(probe.enabled),
      intervalHours: String(probe.interval_hours ?? 168),
      sourceId: probe.source_id || "company-wiki",
      queries: (probe.queries ?? []).join("\n"),
      topK: String(probe.top_k ?? 5),
      budgetUsd: String(probe.budget_usd ?? 1),
      judgeModel: probe.judge_model || "",
      timeoutSeconds: String(probe.timeout_seconds ?? 600),
      resultLimit: String(probe.result_limit ?? 20),
    });
  }

  useEffect(() => {
    if (!isOpen) return;
    if (initialAdminTab) {
      setActiveSection("admin");
      setAdminTab(initialAdminTab);
      return;
    }
    if (initialSection) {
      setActiveSection(initialSection);
    }
  }, [initialAdminTab, initialSection, isOpen]);

  useEffect(() => {
    if (!isOpen || activeSection !== "archive") return;
    let mounted = true;
    setArchiveLoading(true);
    listArchivedChatSessions(apiOptions)
      .then((items) => {
        if (mounted) setArchivedSessions(items);
      })
      .catch(() => {
        if (mounted) setArchivedSessions([]);
      })
      .finally(() => {
        if (mounted) setArchiveLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [activeSection, apiOptions, isOpen]);

  useEffect(() => {
    if (!isOpen || activeSection !== "admin" || adminTab !== "users") return;
    const handle = window.setTimeout(() => {
      listAdminUserCandidates(apiOptions, userSearch, 30)
        .then(setAdminUserCandidates)
        .catch(() => setAdminUserCandidates([]));
    }, 160);
    return () => window.clearTimeout(handle);
  }, [activeSection, adminTab, apiOptions, isOpen, userSearch]);

  useEffect(() => {
    listSkills(apiOptions).then(setSkills).catch(() => setSkills([]));
    listCompanyPrompts(apiOptions).then(setCompanyPrompts).catch(() => setCompanyPrompts([]));
    window.projectR?.prompts?.listUser().then(setUserPrompts).catch(() => setUserPrompts([]));
  }, [serverUrl, token]);

  useEffect(() => {
    if (!isOpen) return;
    if (!window.projectR?.privateWorkspace) {
      setPrivateWorkspace(null);
      setPrivateWorkspaceMessage("本机文件处理仅在桌面客户端可用。");
      return;
    }
    window.projectR.privateWorkspace.getConfig()
      .then((config) => {
        setPrivateWorkspace(config);
        setPrivateWorkspaceMessage("");
      })
      .catch(() => {
        setPrivateWorkspace(null);
        setPrivateWorkspaceMessage("本机文件处理状态读取失败。");
      });
  }, [isOpen]);

  useEffect(() => {
    setProfileDraft({
      nickname: currentUser?.nickname ?? "",
      avatar: currentUser?.avatar ?? "",
    });
  }, [currentUser?.nickname, currentUser?.avatar]);

  useEffect(() => {
    if (!showAvatarPicker) return;

    function handleDocumentMouseDown(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (avatarRef.current?.contains(target)) return;
      if (avatarPickerRef.current?.contains(target)) return;
      setShowAvatarPicker(false);
    }

    function handleDocumentKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setShowAvatarPicker(false);
      }
    }

    document.addEventListener("mousedown", handleDocumentMouseDown);
    document.addEventListener("keydown", handleDocumentKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleDocumentMouseDown);
      document.removeEventListener("keydown", handleDocumentKeyDown);
    };
  }, [showAvatarPicker]);

  useEffect(() => {
    if (openUserMenuId === null) return;

    function handleDocumentKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenUserMenuId(null);
      }
    }

    document.addEventListener("keydown", handleDocumentKeyDown);
    return () => document.removeEventListener("keydown", handleDocumentKeyDown);
  }, [openUserMenuId]);

  useEffect(() => {
    if (activeSection === "admin" && currentUser?.role === "admin") {
      void loadAdminData();
    }
  }, [activeSection, currentUser?.role, serverUrl, token]);

  async function testConnection(targetUrl = draft) {
    const normalized = targetUrl.trim().replace(/\/$/, "");
    if (!normalized) {
      setConnectionState("error");
      setMessage("请先填写后端地址。");
      return false;
    }

    setConnectionState("checking");
    setMessage("正在连接后端...");
    try {
      const health = await apiRequest<HealthResponse>({ baseUrl: normalized }, "/health");
      if (health.status === "ok") {
        setConnectionState("ok");
        setMessage("连接成功，后端健康检查正常。");
        return true;
      }
      setConnectionState("error");
      setMessage(`后端返回异常状态：${health.status}`);
      return false;
    } catch {
      setConnectionState("error");
      setMessage("连接失败，请检查服务器 IP、端口或后端是否已启动。");
      return false;
    }
  }

  async function handleSave() {
    const normalized = draft.trim().replace(/\/$/, "");
    setServerUrl(normalized);
    await testConnection(normalized);
  }

  function updatePreference(next: Partial<PreferenceState>) {
    setPreferences((current) => {
      const merged = { ...current, ...next };
      localStorage.setItem(PREFS_KEY, JSON.stringify(merged));
      if (next.theme) applyTheme(next.theme);
      return merged;
    });
  }

  async function handleSaveProfile() {
    if (!currentUser || currentUser.username === "sysadmin") {
      setMessage("系统内置管理员账号不可修改。");
      return;
    }
    try {
      const updated = await updateCurrentUser(apiOptions, {
        nickname: profileDraft.nickname,
        avatar: profileDraft.avatar,
      });
      refreshCurrentUser(updated);
      setProfileDraft({ nickname: updated.nickname, avatar: updated.avatar });
      setMessage("个人资料已更新。");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "个人资料保存失败。");
    }
  }

  async function handleRestore(sessionId: number) {
    const target = archivedSessions.find((session) => session.id === sessionId);
    if (!target || restoringArchiveId !== null) return;
    setRestoringArchiveId(sessionId);
    try {
      await restoreChatSession(apiOptions, sessionId);
      setArchivedSessions((prev) => prev.filter((s) => s.id !== sessionId));
      await onArchiveRestored?.({ ...target, is_archived: false });
      setMessage(`已恢复「${target.title}」。`);
    } catch {
      setMessage("恢复归档对话失败，请稍后重试。");
    } finally {
      setRestoringArchiveId(null);
    }
  }

  async function handleSaveUserPrompt() {
    const name = promptDraft.name.trim();
    const content = promptDraft.content.trim();
    if (!name || !content) return;
    const saved = await window.projectR?.prompts?.saveUser({
      id: promptDraft.id || undefined,
      name,
      content,
    });
    if (!saved) return;
    const next = await window.projectR?.prompts?.listUser();
    setUserPrompts(next ?? []);
    setPromptDraft({ id: "", name: "", content: "" });
  }

  async function handleAvatarImageUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !currentUser) return;
    if (currentUser.username === "sysadmin") {
      setMessage("系统内置管理员账号不可修改。");
      setShowAvatarPicker(false);
      return;
    }
    try {
      const updated = await uploadCurrentUserAvatar(apiOptions, file);
      refreshCurrentUser(updated);
      setProfileDraft({ nickname: updated.nickname, avatar: updated.avatar });
      setMessage("头像已更新。");
      setShowAvatarPicker(false);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "头像上传失败。");
    }
  }

  async function handleSelectEmoji(emoji: string) {
    if (!currentUser) return;
    if (currentUser.username === "sysadmin") {
      setMessage("系统内置管理员账号不可修改。");
      setShowAvatarPicker(false);
      return;
    }
    try {
      const updated = await updateCurrentUser(apiOptions, { avatar: emoji });
      refreshCurrentUser(updated);
      setProfileDraft({ nickname: updated.nickname, avatar: updated.avatar });
      setMessage("头像已更新。");
      setShowAvatarPicker(false);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "头像保存失败。");
    }
  }

  const COMMON_EMOJIS = [
    "😀", "😎", "🤔", "😊", "🥳", "🤩", "😴", "🤯", "🥶", "🤠",
    "👍", "👏", "🙌", "💪", "🎉", "🔥", "💡", "🚀", "❤️", "🌟",
    "✨", "🎯", "🏆", "🎨", "🎸", "🎮", "📚", "💻", "🔧", "🌈",
  ];

  async function handleDeleteUserPrompt(id: string) {
    const next = await window.projectR?.prompts?.deleteUser(id);
    setUserPrompts(next ?? []);
    if (promptDraft.id === id) setPromptDraft({ id: "", name: "", content: "" });
  }

  async function handleChoosePrivateWorkspaceRoot() {
    if (!window.projectR?.privateWorkspace) return;
    try {
      const config = await window.projectR.privateWorkspace.chooseRoot();
      setPrivateWorkspace(config);
      setPrivateWorkspaceMessage(config.isDefault ? "已使用默认本机文件处理配置。" : "已切换本机文件处理目录。");
    } catch (error) {
      setPrivateWorkspaceMessage(error instanceof Error ? error.message : "本机文件目录选择失败。");
    }
  }

  async function handleOpenPrivateWorkspaceRoot() {
    if (!window.projectR?.privateWorkspace) return;
    try {
      const config = await window.projectR.privateWorkspace.openRoot();
      setPrivateWorkspace(config);
      setPrivateWorkspaceMessage("已打开本机文件处理目录。");
    } catch (error) {
      setPrivateWorkspaceMessage(error instanceof Error ? error.message : "本机文件处理目录打开失败。");
    }
  }

  async function handleResetPrivateWorkspaceRoot() {
    if (!window.projectR?.privateWorkspace) return;
    try {
      const config = await window.projectR.privateWorkspace.resetRoot();
      setPrivateWorkspace(config);
      setPrivateWorkspaceMessage("已恢复默认本机文件处理配置。");
    } catch (error) {
      setPrivateWorkspaceMessage(error instanceof Error ? error.message : "恢复默认本机文件处理配置失败。");
    }
  }

  async function handleQuickDropPrivateWorkspaceFiles() {
    if (!window.projectR?.privateWorkspace) return;
    try {
      const result = await window.projectR.privateWorkspace.quickDrop();
      setPrivateWorkspaceMessage(result.added.length ? `已快速添加 ${result.added.length} 个文件到本机文件处理目录。` : "未选择文件。");
    } catch (error) {
      setPrivateWorkspaceMessage(error instanceof Error ? error.message : "快速添加本机文件失败。");
    }
  }

  // Admin handlers
  async function loadAdminData() {
    setAdminLoading(true);
    setAdminMessage("");
    try {
      const [users, logs, reviews, templateStatus, updateStatus, userCandidates, groupCandidates] = await Promise.all([
        listAdminUsers(apiOptions),
        listAuditLogs(apiOptions, {
          user_id: auditFilter.userId ? Number(auditFilter.userId) : undefined,
          date_from: auditFilter.dateFrom ? new Date(auditFilter.dateFrom).toISOString() : undefined,
          date_to: auditFilter.dateTo ? new Date(`${auditFilter.dateTo}T23:59:59`).toISOString() : undefined,
          limit: 20,
        }),
        listKnowledgeReviews(apiOptions, "pending"),
        listAdminTemplates(apiOptions),
        listClientUpdateReleases(apiOptions),
        listAdminUserCandidates(apiOptions, "", 50),
        listAdminGroupCandidates(apiOptions, "", 50),
      ]);
      setAdminUsers(users);
      setAdminUserCandidates(userCandidates);
      setAdminGroupCandidates(groupCandidates);
      setUserGroupDrafts({});
      setAuditLogs(logs);
      setKnowledgeReviews(reviews);
      setTemplates(templateStatus.items);
      setUpdateReleases(updateStatus.items);
      getKnowledgeStatus(apiOptions).then(setKnowledgeStatus).catch(() => setKnowledgeStatus(null));
      getGBrainMaintenance(apiOptions).then((result) => {
        setGBrainMaintenance(result);
        syncGBrainDreamDraft(result);
      }).catch(() => setGBrainMaintenance(null));
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "管理员数据加载失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleCreateUser() {
    try {
      await createAdminUser(apiOptions, newUser);
      setNewUser({ username: "", nickname: "", password: "", role: "employee", work_group: "" });
      setAdminMessage("用户已创建。");
      await loadAdminData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "创建用户失败。");
    }
  }

  function syncAdminUser(updated: AdminUserResponse) {
    setAdminUsers((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    setUserGroupDrafts((prev) => {
      const next = { ...prev };
      delete next[updated.id];
      return next;
    });
    setEditingUser((prev) => (prev?.id === updated.id ? updated : prev));
    if (currentUser?.user_id === updated.id) {
      refreshCurrentUser({
        ...currentUser,
        role: updated.role,
        nickname: updated.nickname,
        avatar: updated.avatar,
        work_group: updated.work_group,
      });
    }
  }

  function openEditUser(user: AdminUserResponse) {
    if (isSystemAccount(user)) {
      setAdminMessage("sysadmin 是系统内置管理员账号，不能修改。");
      return;
    }
    setEditingUser(user);
    setEditUserDraft({ nickname: user.nickname ?? "" });
    setOpenUserMenuId(null);
  }

  function requestRoleChange(user: AdminUserResponse, nextRole: AdminUserRole) {
    if (user.role === nextRole) return;
    setOpenUserMenuId(null);
    if (isSystemAccount(user)) {
      setAdminMessage("sysadmin 是系统内置管理员账号，角色固定为管理员。");
      return;
    }
    setAdminConfirm({ type: "role", user, nextRole });
  }

  function requestStatusChange(user: AdminUserResponse, nextActive: boolean) {
    if (user.is_active === nextActive) return;
    setOpenUserMenuId(null);
    if (isSystemAccount(user)) {
      setAdminMessage("sysadmin 是系统内置管理员账号，不能停用。");
      return;
    }
    if (currentUser?.user_id === user.id && !nextActive) {
      setAdminMessage("不能停用当前登录账号。");
      return;
    }
    setAdminConfirm({ type: "status", user, nextActive });
  }

  function requestDeleteUser(user: AdminUserResponse) {
    setOpenUserMenuId(null);
    if (isSystemAccount(user)) {
      setAdminMessage("sysadmin 是系统内置管理员账号，不能删除。");
      return;
    }
    if (currentUser?.user_id === user.id) {
      setAdminMessage("不能删除当前登录账号。");
      return;
    }
    setAdminConfirm({ type: "delete", user });
  }

  async function handleSaveEditingUser() {
    if (!editingUser) return;
    if (isSystemAccount(editingUser)) {
      setAdminMessage("sysadmin 是系统内置管理员账号，不能修改。");
      return;
    }
    const nickname = editUserDraft.nickname.trim();
    if ((editingUser.nickname ?? "") === nickname) {
      setAdminMessage("用户资料没有变化。");
      return;
    }
    try {
      const updated = await updateAdminUser(apiOptions, editingUser.id, { nickname });
      syncAdminUser(updated);
      setEditUserDraft({ nickname: updated.nickname ?? "" });
      setAdminMessage("用户资料已更新。");
      await loadAdminData();
      setAdminMessage("用户资料已更新。");
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "更新用户资料失败。");
    }
  }

  async function handleSaveUserGroup(user: AdminUserResponse, value: string) {
    const workGroup = value.trim();
    if (isSystemAccount(user)) {
      setAdminMessage("sysadmin 是系统内置管理员账号，不能修改组别。");
      setUserGroupDrafts((prev) => ({ ...prev, [user.id]: user.work_group ?? "" }));
      return;
    }
    if ((user.work_group ?? "") === workGroup) {
      setUserGroupDrafts((prev) => {
        const next = { ...prev };
        delete next[user.id];
        return next;
      });
      return;
    }
    try {
      const updated = await updateAdminUser(apiOptions, user.id, { work_group: workGroup });
      syncAdminUser(updated);
      setAdminMessage(`已更新 ${userDisplayName(updated)} 的组别。`);
      const groups = await listAdminGroupCandidates(apiOptions, "", 50);
      setAdminGroupCandidates(groups);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "更新用户组别失败。");
    }
  }

  async function handleConfirmAdminAction() {
    if (!adminConfirm) return;
    const pending = adminConfirm;
    try {
      if (pending.type === "delete") {
        const result = await deleteAdminUser(apiOptions, pending.user.id);
        setAdminUsers((prev) => prev.filter((item) => item.id !== result.deleted_user_id));
        setEditingUser((prev) => (prev?.id === result.deleted_user_id ? null : prev));
        setAdminConfirm(null);
        await loadAdminData();
        setAdminMessage(`已删除账号 ${result.deleted_username}。`);
        return;
      }
      const updated =
        pending.type === "role"
          ? await updateAdminUser(apiOptions, pending.user.id, { role: pending.nextRole })
          : await updateAdminUser(apiOptions, pending.user.id, { is_active: pending.nextActive });
      syncAdminUser(updated);
      setAdminConfirm(null);
      await loadAdminData();
      setAdminMessage(
        pending.type === "role"
          ? `已将 ${userDisplayName(updated)} 的角色改为 ${roleLabel(updated.role)}。`
          : `已${updated.is_active ? "启用" : "停用"} ${userDisplayName(updated)}。`,
      );
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "用户操作失败。");
    }
  }

  function openPasswordDialog(user: AdminUserResponse) {
    setOpenUserMenuId(null);
    if (isSystemAccount(user)) {
      setAdminMessage("sysadmin 是系统内置管理员账号，密码固定为 Admin123。");
      return;
    }
    setPasswordDialog({
      user,
      password: generateTemporaryPassword(),
      resultPassword: null,
      copied: false,
    });
  }

  async function handleConfirmPasswordReset() {
    if (!passwordDialog) return;
    const password = passwordDialog.password.trim();
    if (password.length < 8) {
      setAdminMessage("新密码至少需要 8 位。");
      return;
    }
    try {
      await resetAdminUserPassword(apiOptions, passwordDialog.user.id, password);
      await loadAdminData();
      setPasswordDialog((prev) => (prev ? { ...prev, password, resultPassword: password, copied: false } : prev));
      setAdminMessage("密码已重置，请复制后再关闭。");
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "重置密码失败。");
    }
  }

  async function handleCopyResetPassword() {
    if (!passwordDialog?.resultPassword) return;
    try {
      await navigator.clipboard.writeText(passwordDialog.resultPassword);
      setPasswordDialog((prev) => (prev ? { ...prev, copied: true } : prev));
    } catch {
      setAdminMessage("复制失败，请手动选中新密码。");
    }
  }

  async function handleReviewKnowledge(item: KnowledgeReviewResponse, status: "approved" | "rejected") {
    let content: string | undefined;
    if (status === "approved") {
      const edited = window.prompt("确认或修改后写入正式知识库", item.content);
      if (edited === null) return;
      content = edited;
    }
    try {
      await reviewKnowledge(apiOptions, item.id, status, content);
      await loadAdminData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "知识审核失败。");
    }
  }

  async function handleSubmitReviewCitationFixer(item: KnowledgeReviewResponse) {
    setAdminLoading(true);
    setAdminMessage(`正在为审核项 #${item.id} 提交 GBrain citation-fixer...`);
    try {
      const result = await submitKnowledgeReviewCitationFixer(apiOptions, item.id, {});
      const job = asRecord(result.result?.result);
      const jobId = recordNumber(job, "id") ?? result.tracking?.tracked_job?.job_id ?? result.tracked_job?.job_id;
      setAdminMessage(
        result.ok
          ? `审核项 #${item.id} 已提交引用修复${jobId ? `：#${jobId}` : ""}。`
          : `审核项 #${item.id} 引用修复提交失败：${result.status}。`,
      );
      await loadAdminData();
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "提交审核项引用修复失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRefreshKnowledge(enablePdfStructuredExtraction?: boolean) {
    setAdminLoading(true);
    setAdminMessage(enablePdfStructuredExtraction ? "正在结构化提炼 PDF 并刷新知识库..." : "正在刷新知识库...");
    try {
      const result = await refreshKnowledge(apiOptions, enablePdfStructuredExtraction);
      setAdminMessage(
        result.ok
          ? `刷新完成：${result.indexed} 个文件，${result.chunks} 个片段，新增 ${result.pending_reviews_created ?? 0} 条待审核。`
          : result.error ?? "刷新失败。",
      );
      setKnowledgeStatus(await getKnowledgeStatus(apiOptions));
      const maintenance = await getGBrainMaintenance(apiOptions);
      setGBrainMaintenance(maintenance);
      syncGBrainDreamDraft(maintenance);
      syncGBrainContradictionDraft(maintenance);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "刷新知识库失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRunKnowledgeQualityReport(includeThink = false) {
    setAdminLoading(true);
    setAdminMessage(includeThink ? "正在运行 GBrain Think 质量报告..." : "正在运行 GBrain 查询质量报告...");
    try {
      const result = await runKnowledgeRegression(apiOptions, includeThink);
      setAdminMessage(
        result.ok
          ? `质量报告完成：query ${result.query.passed}/${result.query.total}，think ${result.think.passed}/${result.think.total}${result.id ? `，报告 ${result.id}` : ""}。`
          : `质量报告存在失败：query ${result.query.passed}/${result.query.total}，think ${result.think.passed}/${result.think.total}。`,
      );
      setKnowledgeStatus(await getKnowledgeStatus(apiOptions));
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "运行 GBrain 质量报告失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleExportKnowledgeQualityReport(reportId?: string | null) {
    const targetReportId = reportId || knowledgeStatus?.quality_reports?.latest?.id || "latest";
    setAdminLoading(true);
    setAdminMessage("正在导出 GBrain 质量报告...");
    try {
      const report = await getKnowledgeQualityReport(apiOptions, targetReportId);
      const filename = `${report.id || targetReportId || "gbrain-quality-report"}.json`.replace(/[\\/:*?"<>|]/g, "_");
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setAdminMessage(`已导出质量报告：${report.id || targetReportId}。`);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "导出 GBrain 质量报告失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleStartGBrain() {
    setAdminLoading(true);
    setAdminMessage("正在启动 GBrain...");
    try {
      const result = await startGBrainService(apiOptions);
      setAdminMessage(result.ok ? `GBrain ${statusLabel(result.status)}。` : result.error ?? `GBrain ${statusLabel(result.status)}。`);
      setKnowledgeStatus(await getKnowledgeStatus(apiOptions));
      const maintenance = await getGBrainMaintenance(apiOptions);
      setGBrainMaintenance(maintenance);
      syncGBrainDreamDraft(maintenance);
      syncGBrainContradictionDraft(maintenance);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "启动 GBrain 失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRestartGBrain() {
    setAdminLoading(true);
    setAdminMessage("正在重启 GBrain...");
    try {
      const result = await restartGBrainService(apiOptions);
      setAdminMessage(result.ok ? "GBrain 已重启。" : result.error ?? "GBrain 重启失败。");
      setKnowledgeStatus(await getKnowledgeStatus(apiOptions));
      const maintenance = await getGBrainMaintenance(apiOptions);
      setGBrainMaintenance(maintenance);
      syncGBrainDreamDraft(maintenance);
      syncGBrainContradictionDraft(maintenance);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "重启 GBrain 失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function loadGBrainMaintenanceData(message = "") {
    if (message) setAdminMessage(message);
    const result = await getGBrainMaintenance(apiOptions);
    setGBrainMaintenance(result);
    syncGBrainDreamDraft(result);
    syncGBrainContradictionDraft(result);
    return result;
  }

  async function handleRefreshGBrainMaintenance() {
    setAdminLoading(true);
    try {
      await loadGBrainMaintenanceData("GBrain 维护状态已刷新。");
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "刷新 GBrain 维护状态失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleGBrainMaintenanceCheck() {
    setAdminLoading(true);
    setAdminMessage("正在运行 GBrain 维护检查...");
    try {
      const result = await runGBrainMaintenanceCheck(apiOptions, 90);
      setAdminMessage(result.ok ? "GBrain 维护检查完成。" : "GBrain 维护检查失败。");
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "GBrain 维护检查失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleSaveGBrainDreamCycle() {
    setAdminLoading(true);
    setAdminMessage("正在保存 GBrain Dream Cycle 配置...");
    const intervalHours = Number(gbrainDreamDraft.intervalHours || "168");
    const targetScore = Number(gbrainDreamDraft.targetScore || "90");
    const jobNames = gbrainDreamDraft.jobNames.split(",").map((item) => item.trim()).filter(Boolean);
    try {
      const result = await updateGBrainDreamCycle(apiOptions, {
        enabled: gbrainDreamDraft.enabled,
        interval_hours: Number.isFinite(intervalHours) ? Math.max(1, Math.min(intervalHours, 2160)) : 168,
        target_score: Number.isFinite(targetScore) ? Math.max(1, Math.min(targetScore, 100)) : 90,
        source_id: gbrainDreamDraft.sourceId.trim() || "company-wiki",
        job_names: jobNames.length ? jobNames : ["autopilot-cycle"],
      });
      setAdminMessage("GBrain Dream Cycle 配置已保存。");
      const nextMaintenance = gbrainMaintenance
        ? { ...gbrainMaintenance, dream_cycle: result.config }
        : ({ ok: true, dream_cycle: result.config } as GBrainMaintenanceResponse);
      setGBrainMaintenance(nextMaintenance);
      syncGBrainDreamDraft(nextMaintenance);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "保存 GBrain Dream Cycle 配置失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRunGBrainDreamCycle() {
    setAdminLoading(true);
    setAdminMessage("正在手动运行 GBrain Dream Cycle...");
    try {
      const result = await runGBrainDreamCycle(apiOptions, true);
      setAdminMessage(result.ran ? `GBrain Dream Cycle 已运行：${result.status}。` : `GBrain Dream Cycle 未运行：${result.status}。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "运行 GBrain Dream Cycle 失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleTickGBrainDreamCycle() {
    setAdminLoading(true);
    setAdminMessage("正在检查 GBrain Dream Cycle 是否到期...");
    try {
      const result = await tickGBrainDreamCycle(apiOptions);
      setAdminMessage(result.ran ? `GBrain Dream Cycle 到期已执行：${result.status}。` : `GBrain Dream Cycle 未执行：${result.status}。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "检查 GBrain Dream Cycle 到期状态失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handlePollGBrainDreamCycleJobs() {
    setAdminLoading(true);
    setAdminMessage("正在轮询 GBrain Dream Cycle 任务状态...");
    try {
      const result = await pollGBrainDreamCycleJobs(apiOptions);
      setAdminMessage(`GBrain Dream Cycle 已检查 ${result.checked} 个任务，状态变化 ${result.transitions.length} 个。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "轮询 GBrain Dream Cycle 任务失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRestartGBrainDreamCycleWorker() {
    setAdminLoading(true);
    setAdminMessage("正在重启 GBrain Dream Cycle Worker...");
    try {
      const result = await restartGBrainDreamCycleWorker(apiOptions);
      setAdminMessage(result.ok ? "GBrain Dream Cycle Worker 已重启。" : "GBrain Dream Cycle Worker 未运行。");
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "重启 GBrain Dream Cycle Worker 失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleSaveGBrainContradictionProbe() {
    setAdminLoading(true);
    setAdminMessage("正在保存 GBrain 冲突探针配置...");
    const intervalHours = Number(gbrainContradictionDraft.intervalHours || "168");
    const topK = Number(gbrainContradictionDraft.topK || "5");
    const budgetUsd = Number(gbrainContradictionDraft.budgetUsd || "1");
    const timeoutSeconds = Number(gbrainContradictionDraft.timeoutSeconds || "600");
    const resultLimit = Number(gbrainContradictionDraft.resultLimit || "20");
    const queries = gbrainContradictionDraft.queries
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    try {
      const result = await updateGBrainContradictionProbe(apiOptions, {
        enabled: gbrainContradictionDraft.enabled,
        interval_hours: Number.isFinite(intervalHours) ? Math.max(1, Math.min(intervalHours, 2160)) : 168,
        source_id: gbrainContradictionDraft.sourceId.trim() || "company-wiki",
        queries,
        top_k: Number.isFinite(topK) ? Math.max(1, Math.min(topK, 20)) : 5,
        budget_usd: Number.isFinite(budgetUsd) ? Math.max(0.01, Math.min(budgetUsd, 100)) : 1,
        judge_model: gbrainContradictionDraft.judgeModel.trim() || null,
        timeout_seconds: Number.isFinite(timeoutSeconds) ? Math.max(30, Math.min(timeoutSeconds, 3600)) : 600,
        result_limit: Number.isFinite(resultLimit) ? Math.max(1, Math.min(resultLimit, 100)) : 20,
      });
      setAdminMessage("GBrain 冲突探针配置已保存。");
      const nextMaintenance = gbrainMaintenance
        ? { ...gbrainMaintenance, contradiction_probe: result.config }
        : ({ ok: true, contradiction_probe: result.config } as GBrainMaintenanceResponse);
      setGBrainMaintenance(nextMaintenance);
      syncGBrainContradictionDraft(nextMaintenance);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "保存 GBrain 冲突探针配置失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRunGBrainContradictionProbe() {
    setAdminLoading(true);
    setAdminMessage("正在运行 GBrain 冲突探针...");
    try {
      const result = await runGBrainContradictionProbe(apiOptions, true);
      const flagged = recordNumber(asRecord(result.summary), "total_contradictions_flagged");
      setAdminMessage(result.ran ? `GBrain 冲突探针已运行：${result.status}，疑似冲突 ${flagged ?? 0}。` : `GBrain 冲突探针未运行：${result.status}。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "运行 GBrain 冲突探针失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleTickGBrainContradictionProbe() {
    setAdminLoading(true);
    setAdminMessage("正在检查 GBrain 冲突探针是否到期...");
    try {
      const result = await tickGBrainContradictionProbe(apiOptions);
      const flagged = recordNumber(asRecord(result.summary), "total_contradictions_flagged");
      setAdminMessage(result.ran ? `GBrain 冲突探针到期已运行：${result.status}，疑似冲突 ${flagged ?? 0}。` : `GBrain 冲突探针未运行：${result.status}。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "检查 GBrain 冲突探针到期状态失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleLoadGBrainGraph() {
    setAdminLoading(true);
    setAdminMessage("正在加载 GBrain 关系图谱...");
    try {
      const result = await getGBrainGraph(apiOptions, {
        source_id: gbrainGraphDraft.sourceId.trim() || CUSTOMER_INTELLIGENCE_SOURCE_ID,
        focus: gbrainGraphDraft.focus.trim() || undefined,
        entity_type: gbrainGraphDraft.entityType.trim() || undefined,
        limit: 120,
      });
      setGBrainGraph(result);
      const warning = result.warnings?.find((item) => item.trim());
      setAdminMessage(result.ok ? "GBrain 关系图谱已加载。" : warning || "GBrain 关系图谱加载失败。");
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "加载 GBrain 关系图谱失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleLoadGBrainEntityMergeCandidates() {
    setAdminLoading(true);
    setAdminMessage("正在加载 GBrain 实体合并候选...");
    try {
      const result = await getGBrainEntityMergeCandidates(apiOptions, {
        source_id: gbrainGraphDraft.sourceId.trim() || CUSTOMER_INTELLIGENCE_SOURCE_ID,
        focus: gbrainGraphDraft.focus.trim() || undefined,
        limit: 80,
      });
      setGBrainEntityMerge(result);
      const warning = result.warnings?.find((item) => item.trim());
      setAdminMessage(result.ok ? "GBrain 实体合并候选已加载。" : warning || "GBrain 实体合并候选加载失败。");
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "加载 GBrain 实体合并候选失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleApplyGBrainEntityMergeCandidate(candidate: GBrainEntityMergeCandidate, action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes") {
    setAdminLoading(true);
    setAdminMessage(
      action === "dismiss"
        ? "正在忽略实体候选..."
        : action === "record_alias"
          ? "正在记录实体别名并同步 GBrain..."
          : action === "apply_relink_changes"
            ? "正在应用实体引用改写并同步 GBrain..."
            : "正在创建实体页并同步 GBrain...",
    );
    try {
      const result = await applyGBrainEntityMergeCandidateAction(apiOptions, {
        source_id: candidate.source_id,
        candidate_id: candidate.id,
        action,
      });
      const syncStatus = result.sync?.status ? `，sync=${result.sync.status}` : "";
      setAdminMessage(
        result.ok
          ? `实体候选已处理：${result.status}${result.created_file ? `，${result.created_file}` : ""}${syncStatus}。`
          : result.error || "实体候选处理失败。",
      );
      const refreshed = await getGBrainEntityMergeCandidates(apiOptions, {
        source_id: gbrainGraphDraft.sourceId.trim() || candidate.source_id,
        focus: gbrainGraphDraft.focus.trim() || undefined,
        limit: 80,
      });
      setGBrainEntityMerge(refreshed);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "实体候选处理失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handlePreviewGBrainEntityMergeCandidate(candidate: GBrainEntityMergeCandidate) {
    setAdminLoading(true);
    setAdminMessage("正在生成 GBrain 实体合并预览...");
    try {
      const result = await getGBrainEntityMergeCandidatePreview(apiOptions, {
        source_id: candidate.source_id,
        candidate_id: candidate.id,
      });
      setGBrainEntityMergePreview(result);
      setAdminMessage(`实体合并预览已生成：${result.stats?.planned_relink_changes ?? 0} 条引用建议。`);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "实体合并预览失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleSubmitGBrainJob(name: "sync" | "embed" | "lint" | "backlinks") {
    setAdminLoading(true);
    setAdminMessage(`正在提交 GBrain ${name} 任务...`);
    const sourceId = knowledgeStatus?.source_id || "company-wiki";
    const derivedDir = knowledgeStatus?.source_dirs?.[0] || ".";
    const dataByName: Record<typeof name, Record<string, unknown>> = {
      sync: { sourceId, repoPath: derivedDir, noPull: true, noEmbed: false },
      embed: { all: true },
      lint: { dir: derivedDir, dryRun: true },
      backlinks: { dir: derivedDir, action: "check", dryRun: true },
    };
    try {
      const result = await submitGBrainJob(apiOptions, { name, data: dataByName[name] });
      setAdminMessage(result.status === "ok" ? `GBrain ${name} 任务已提交。` : result.error || `GBrain ${name} 任务提交失败。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : `GBrain ${name} 任务提交失败。`);
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleCancelGBrainJob(jobId: number) {
    setAdminLoading(true);
    try {
      const result = await cancelGBrainJob(apiOptions, jobId);
      setAdminMessage(result.status === "ok" ? `GBrain 任务 #${jobId} 已取消。` : result.error || `GBrain 任务 #${jobId} 取消失败。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "取消 GBrain 任务失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRetryGBrainJob(jobId: number) {
    setAdminLoading(true);
    try {
      const result = await retryGBrainJob(apiOptions, jobId);
      setAdminMessage(result.status === "ok" ? `GBrain 任务 #${jobId} 已重试。` : result.error || `GBrain 任务 #${jobId} 重试失败。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "重试 GBrain 任务失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleSubmitCitationFixer() {
    setAdminLoading(true);
    setAdminMessage("正在提交 GBrain citation-fixer...");
    const reviewId = citationFixerDraft.reviewId.trim() ? Number(citationFixerDraft.reviewId.trim()) : null;
    const maxTurns = Number(citationFixerDraft.maxTurns.trim() || "30");
    const allowedSlugPrefixes = citationFixerDraft.slugPrefixes
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    try {
      const result = await submitGBrainCitationFixer(apiOptions, {
        page_slug: citationFixerDraft.pageSlug.trim() || null,
        review_id: Number.isFinite(reviewId) ? reviewId : null,
        notes: citationFixerDraft.notes.trim() || null,
        allowed_slug_prefixes: allowedSlugPrefixes,
        max_turns: Number.isFinite(maxTurns) ? Math.max(1, Math.min(maxTurns, 100)) : 30,
      });
      const job = asRecord(result.result);
      const jobId = recordNumber(job, "id");
      setAdminMessage(
        result.status === "ok"
          ? `GBrain citation-fixer 已提交${jobId ? `：#${jobId}` : ""}。`
          : result.error || "GBrain citation-fixer 提交失败。",
      );
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "GBrain citation-fixer 提交失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handlePollGBrainCitationFixerJobs() {
    setAdminLoading(true);
    setAdminMessage("正在轮询 GBrain citation-fixer 任务状态...");
    try {
      const result = await pollGBrainCitationFixerJobs(apiOptions);
      setAdminMessage(`GBrain citation-fixer 已检查 ${result.checked} 个任务，状态变化 ${result.transitions.length} 个。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "轮询 GBrain citation-fixer 任务失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleRollbackGBrainCitationFixerJob(jobId: number) {
    setAdminLoading(true);
    setAdminMessage(`正在回滚 GBrain citation-fixer 任务 #${jobId}...`);
    try {
      const result = await rollbackGBrainCitationFixerJob(apiOptions, jobId);
      setAdminMessage(result.ok ? `GBrain citation-fixer #${jobId} 已回滚。` : `GBrain citation-fixer #${jobId} 回滚失败：${result.status}。`);
      await loadGBrainMaintenanceData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "回滚 GBrain citation-fixer 任务失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleUploadUpdateRelease() {
    const version = updateDraft.version.trim();
    if (!version || !updateFile) {
      setAdminMessage("请填写版本号并选择安装包文件。");
      return;
    }
    setAdminLoading(true);
    setAdminMessage("正在上传更新包...");
    try {
      await uploadClientUpdateRelease(apiOptions, {
        version,
        releaseNotes: updateDraft.releaseNotes,
        minimumSupportedVersion: updateDraft.minimumSupportedVersion,
        platform: updateDraft.platform,
        isForceUpdate: updateDraft.isForceUpdate,
        isActive: updateDraft.isActive,
        file: updateFile,
      });
      setUpdateDraft({
        version: "",
        minimumSupportedVersion: "",
        platform: "win32",
        releaseNotes: "",
        isForceUpdate: false,
        isActive: true,
      });
      setUpdateFile(null);
      if (updateFileInputRef.current) updateFileInputRef.current.value = "";
      setAdminMessage("更新包已登记。");
      await loadAdminData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "更新包上传失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  // Admin pagination / filter helpers
  function paginate<T>(items: T[], page: number, pageSize: number): T[] {
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }

  function filterUsers(users: AdminUserResponse[], search: string): AdminUserResponse[] {
    if (!search.trim()) return users;
    const s = search.toLowerCase();
    return users.filter((u) => u.username.toLowerCase().includes(s) || (u.nickname ?? "").toLowerCase().includes(s));
  }

  function sortUsers(users: AdminUserResponse[], sort: { field: "username" | "created_at"; dir: "asc" | "desc" }): AdminUserResponse[] {
    return [...users].sort((a, b) => {
      if (a.is_active !== b.is_active) {
        return a.is_active ? -1 : 1;
      }
      let cmp = 0;
      if (sort.field === "username") {
        cmp = a.username.localeCompare(b.username);
      } else if (sort.field === "created_at") {
        cmp = parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime();
      }
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }

  function filterReviews(reviews: KnowledgeReviewResponse[], search: string): KnowledgeReviewResponse[] {
    if (!search.trim()) return reviews;
    const s = search.toLowerCase();
    return reviews.filter((r) => (r.source ?? "").toLowerCase().includes(s) || r.content.toLowerCase().includes(s));
  }

  function canSubmitReviewCitationFixer(item: KnowledgeReviewResponse) {
    return item.source.startsWith("gbrain_answer_correction:") || item.source.startsWith("gbrain_think_review:");
  }

  function filterTemplates(templates: AdminTemplateStatusResponse["items"], search: string): AdminTemplateStatusResponse["items"] {
    if (!search.trim()) return templates;
    const s = search.toLowerCase();
    return templates.filter((t) => t.display_name.toLowerCase().includes(s) || t.skill_name.toLowerCase().includes(s));
  }

  function filterAuditLogs(logs: AuditLogResponse[], search: string, actionType: string): AuditLogResponse[] {
    let result = logs;
    if (actionType) {
      result = result.filter((l) => l.action === actionType);
    }
    if (!search.trim()) return result;
    const s = search.toLowerCase();
    return result.filter((l) => l.action.toLowerCase().includes(s) || (l.detail ?? "").toLowerCase().includes(s));
  }

  const uniqueAuditActions = Array.from(new Set(auditLogs.map((l) => l.action))).sort();

  const baseSections: Array<{ id: SettingsSection; label: string; icon: React.ReactNode }> = [
    { id: "general", label: "通用", icon: <SettingsIcon /> },
    { id: "server", label: "服务器", icon: <BrainIcon /> },
    { id: "prompts", label: "提示词", icon: <PromptIcon /> },
    { id: "archive", label: "归档", icon: <ArchiveIcon /> },
    { id: "agent", label: "Agent", icon: <AgentIcon /> },
    { id: "remote", label: "远程连接", icon: <SendIcon /> },
    { id: "tutorial", label: "教程", icon: <NoteIcon /> },
    { id: "shortcuts", label: "快捷键", icon: <EditIcon /> },
  ];

  const visibleSections = currentUser?.role === "admin"
    ? [...baseSections, { id: "admin" as SettingsSection, label: "管理员", icon: <ShieldIcon /> }]
    : baseSections;

  if (!isOpen) return null;

  const activeLabel = SECTION_LABELS[activeSection];

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="settings-dialog-header">
          <span className="settings-dialog-title">{activeLabel}</span>
          <button className="settings-dialog-close" onClick={onClose} title="关闭" type="button">
            <XmarkIcon />
          </button>
        </div>

        <div className="settings-dialog-body">
          <nav className="settings-dialog-nav">
            {visibleSections.map((section) => (
              <button
                className={activeSection === section.id ? "is-active" : ""}
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                type="button"
              >
                <span className="settings-nav-icon">{section.icon}</span>
                <span>{section.label}</span>
              </button>
            ))}
          </nav>

          <div className="settings-dialog-content">
            {activeSection === "general" ? (
              <>
                <div className="settings-section">
                  <div className="settings-section-header">
                    <h3>用户档案</h3>
                    <p>设置你的头像和显示名称</p>
                  </div>
                  <div className="settings-card">
                    <div className="settings-card-row" style={{ gap: 16, position: "relative" }}>
                      <div
                        ref={avatarRef}
                        className={`profile-avatar ${profileLocked ? "is-locked" : ""}`}
                        onClick={() => {
                          if (profileLocked) {
                            setMessage("系统内置管理员账号不可修改。");
                            return;
                          }
                          const rect = avatarRef.current?.getBoundingClientRect();
                          if (rect) {
                            const pickerWidth = 280;
                            const viewportPadding = 12;
                            const maxLeft = Math.max(
                              viewportPadding,
                              window.innerWidth - pickerWidth - viewportPadding,
                            );
                            const left = Math.min(
                              Math.max(viewportPadding, rect.left),
                              maxLeft,
                            );
                            setPickerPos({ top: rect.bottom + 8, left });
                          }
                          setShowAvatarPicker((prev) => !prev);
                        }}
                        title={profileLocked ? "系统内置管理员账号不可修改" : "更换头像"}
                        style={{ cursor: profileLocked ? "default" : "pointer", position: "relative", width: 64, height: 64, borderRadius: "20%", overflow: "hidden", flexShrink: 0, display: "grid", placeItems: "center", background: "hsl(var(--muted))", fontSize: 28 }}
                      >
                        {profileAvatarUrl ? (
                          <img src={profileAvatarUrl} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        ) : (
                          <span>{profileDraft.avatar || "👤"}</span>
                        )}
                        <div
                          style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", background: "rgba(0,0,0,0.4)", opacity: 0, transition: "opacity 0.15s", pointerEvents: "none" }}
                          className="profile-avatar-overlay"
                        >
                          <CameraIcon className="profile-avatar-camera" />
                        </div>
                      </div>

                      {showAvatarPicker && pickerPos && (
                        <div className="profile-avatar-picker" ref={avatarPickerRef} style={{ top: pickerPos.top, left: pickerPos.left }}>
                          <div className="profile-avatar-picker-grid">
                            {COMMON_EMOJIS.map((emoji) => (
                              <button key={emoji} onClick={() => handleSelectEmoji(emoji)} type="button">
                                {emoji}
                              </button>
                            ))}
                          </div>
                          <div className="profile-avatar-picker-upload">
                            <button onClick={() => fileInputRef.current?.click()} type="button">
                              上传自定义图片
                            </button>
                            <input
                              ref={fileInputRef}
                              type="file"
                              accept="image/png,image/jpeg,image/gif,image/webp"
                              style={{ display: "none" }}
                              onChange={handleAvatarImageUpload}
                            />
                          </div>
                        </div>
                      )}

                      <div style={{ flex: 1, minWidth: 0 }}>
                        {isEditingName ? (
                          <input
                            type="text"
                            value={nameInput}
                            onChange={(e) => setNameInput(e.target.value)}
                            onBlur={() => {
                              const trimmed = nameInput.trim();
                              if (trimmed && trimmed !== currentUser?.nickname) {
                                void updateCurrentUser(apiOptions, { nickname: trimmed })
                                  .then((updated) => {
                                    refreshCurrentUser(updated);
                                    setProfileDraft((prev) => ({ ...prev, nickname: trimmed }));
                                  })
                                  .catch(() => {});
                              }
                              setIsEditingName(false);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.currentTarget.blur();
                              } else if (e.key === "Escape") {
                                setNameInput(currentUser?.nickname ?? "");
                                setIsEditingName(false);
                              }
                            }}
                            autoFocus
                            style={{ fontSize: 18, fontWeight: 600, color: "hsl(var(--foreground))", background: "transparent", border: "none", borderBottom: "2px solid hsl(var(--foreground))", outline: "none", width: "100%", maxWidth: 240, padding: "2px 0" }}
                          />
                        ) : (
                          <button
                            onClick={() => {
                              if (profileLocked) {
                                setMessage("系统内置管理员账号不可修改。");
                                return;
                              }
                              setNameInput(profileDraft.nickname);
                              setIsEditingName(true);
                            }}
                            style={{ fontSize: 18, fontWeight: 600, color: "hsl(var(--foreground))", background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
                          >
                            <span>{profileDraft.nickname || currentUser?.nickname || "未设置昵称"}</span>
                            <EditIcon className="profile-name-edit-icon" />
                          </button>
                        )}
                        <div className="profile-meta-row">
                          <span>账号 {currentUser?.username ?? "-"}</span>
                          <span>最近登录 {formatOptionalDate(currentUser?.last_login_at)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-header">
                    <h3>本机文件</h3>
                    <p>从任意本机路径按次选择文件；不再使用固定私人空间目录作为产品入口</p>
                  </div>
                  <div className="settings-card private-workspace-card">
                    <div className="settings-card-row settings-path-row">
                      <div className="settings-row-info">
                        <strong>本机文件处理</strong>
                        <span>{window.projectR?.privateWorkspace ? "可用：支持本机文件摘录、图片预览和发送前授权" : "仅桌面客户端可用"}</span>
                      </div>
                      <div className="settings-row-control private-workspace-actions">
                        <span className="settings-inline-note">在聊天输入框使用附件按钮选择文件。</span>
                      </div>
                    </div>
                    {privateWorkspaceMessage ? (
                      <p className="private-workspace-message">{privateWorkspaceMessage}</p>
                    ) : null}
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-header">
                    <h3>通用设置</h3>
                    <p>应用的基本配置</p>
                  </div>
                  <div className="settings-card">
                    <div className="settings-option-row">
                      <div>
                        <strong>界面语言</strong>
                        <span>更多语言支持即将推出</span>
                      </div>
                      <select disabled value="zh-CN">
                        <option value="zh-CN">简体中文</option>
                      </select>
                    </div>
                    <div className="settings-option-row">
                      <div>
                        <strong>任务完成音效</strong>
                        <span>Agent 工作流完成后播放提示音</span>
                      </div>
                      <label className="toggle-switch">
                        <input
                          checked={preferences.completionSound}
                          onChange={(event) => updatePreference({ completionSound: event.target.checked })}
                          type="checkbox"
                        />
                        <span className="toggle-switch-slider" />
                      </label>
                    </div>
                    <div className="settings-option-row">
                      <div>
                        <strong>自动归档</strong>
                        <span>按最后更新时间清理侧栏会话</span>
                      </div>
                      <select
                        value={preferences.autoArchiveDays}
                        onChange={(event) => updatePreference({ autoArchiveDays: event.target.value })}
                      >
                        <option value="disabled">禁用</option>
                        <option value="7">7 天</option>
                        <option value="14">14 天</option>
                        <option value="30">30 天</option>
                        <option value="60">60 天</option>
                      </select>
                    </div>
                    <div className="settings-option-row">
                      <div>
                        <strong>消息悬浮置顶条</strong>
                        <span>会话滚动时保留置顶提示入口</span>
                      </div>
                      <label className="toggle-switch">
                        <input
                          checked={preferences.floatingPinBar}
                          onChange={(event) => updatePreference({ floatingPinBar: event.target.checked })}
                          type="checkbox"
                        />
                        <span className="toggle-switch-slider" />
                      </label>
                    </div>
                    <div className="settings-option-row">
                      <div>
                        <strong>外观主题</strong>
                        <span>亮色、暗色或跟随系统</span>
                      </div>
                      <select
                        value={preferences.theme}
                        onChange={(event) => updatePreference({ theme: event.target.value as PreferenceState["theme"] })}
                      >
                        <option value="system">跟随系统</option>
                        <option value="light">亮色</option>
                        <option value="dark">暗色</option>
                      </select>
                    </div>
                  </div>
                </div>
              </>
            ) : null}

            {activeSection === "server" ? (
              <div className="settings-section">
                <div className="settings-section-header">
                  <h3>服务器连接</h3>
                  <p>后端地址由本地配置管理，保存后会立即检查连接状态</p>
                </div>
                <div className="settings-card">
                  <div className="settings-card-row">
                    <div className="settings-row-info">
                      <strong>后端地址</strong>
                    </div>
                    <div className="settings-row-control">
                      <input
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        style={{ minWidth: 260, height: 34, padding: "0 10px", border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--background))", color: "hsl(var(--foreground))", fontSize: 13 }}
                      />
                    </div>
                  </div>
                  <div className="settings-card-row">
                    <div className="settings-row-info">
                      {message ? <p className={`connection-status connection-status-${connectionState}`}>{message}</p> : <span />}
                    </div>
                    <div className="settings-row-control" style={{ gap: 8 }}>
                      <button onClick={handleSave}>保存并测试</button>
                      <button className="ghost-button" onClick={() => void testConnection()} type="button">
                        仅测试连接
                      </button>
                    </div>
                  </div>
                </div>
                <p className="meta" style={{ marginTop: 8 }}>当前生效：{serverUrl}</p>
              </div>
            ) : null}

            {activeSection === "archive" ? (
              <div className="settings-section">
                <div className="settings-section-header">
                  <h3>归档管理</h3>
                  <p>归档的对话不会出现在侧栏中，但可以在此恢复</p>
                </div>
                <div className="settings-card">
                  {archiveLoading ? (
                    <div className="settings-card-row">
                      <span className="meta">正在加载...</span>
                    </div>
                  ) : archivedSessions.length === 0 ? (
                    <div className="settings-card-row">
                      <span className="meta">暂无已归档对话。</span>
                    </div>
                  ) : (
                    archivedSessions.map((s) => (
                      <div className="settings-card-row" key={s.id}>
                        <div className="settings-row-info">
                          <strong>{s.title}</strong>
                          <span>{formatDate(s.updated_at)}</span>
                        </div>
                        <div className="settings-row-control">
                          <button
                            className="ghost-button"
                            disabled={restoringArchiveId !== null}
                            onClick={() => void handleRestore(s.id)}
                            type="button"
                          >
                            {restoringArchiveId === s.id ? "恢复中..." : "恢复"}
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : null}

            {activeSection === "prompts" ? (
              <>
                <div className="settings-section">
                  <div className="settings-section-header">
                    <h3>内置提示词</h3>
                    <p>系统默认，只读</p>
                  </div>
                  <div className="settings-card">
                    <div className="settings-card-row">
                      <div className="settings-row-info">
                        <strong>{PROJECT_R_BUILTIN_PROMPT.name}</strong>
                        <span>Project_R 默认，只读</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-header">
                    <h3>公司预设</h3>
                    <p>后端预设，只读</p>
                  </div>
                  <div className="settings-card">
                    {companyPrompts.map((prompt) => (
                      <div className="settings-card-row" key={prompt.id}>
                        <div className="settings-row-info">
                          <strong>{prompt.name}</strong>
                          <span>{prompt.description || "后端预设，只读"}</span>
                        </div>
                      </div>
                    ))}
                    {companyPrompts.length === 0 ? (
                      <div className="settings-card-row">
                        <span className="meta">暂无公司预设。</span>
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="settings-section">
                  <div className="settings-section-header">
                    <h3>本机自定义</h3>
                    <p>仅保存在本机，不上传后端</p>
                  </div>
                  <div className="settings-card">
                    <div className="settings-card-row" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
                      <input
                        placeholder="提示词名称"
                        value={promptDraft.name}
                        onChange={(event) => setPromptDraft((prev) => ({ ...prev, name: event.target.value }))}
                        style={{ width: "100%", height: 36, padding: "0 10px", border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--background))", color: "hsl(var(--foreground))", fontSize: 13 }}
                      />
                      <textarea
                        placeholder="输入系统提示词内容..."
                        value={promptDraft.content}
                        onChange={(event) => setPromptDraft((prev) => ({ ...prev, content: event.target.value }))}
                        style={{ width: "100%", minHeight: 120, padding: 10, border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--background))", color: "hsl(var(--foreground))", fontSize: 13, resize: "vertical", lineHeight: 1.6 }}
                      />
                      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                        <button disabled={!promptDraft.name.trim() || !promptDraft.content.trim()} onClick={() => void handleSaveUserPrompt()} type="button">
                          {promptDraft.id ? "保存修改" : "新建提示词"}
                        </button>
                        {promptDraft.id ? (
                          <button className="ghost-button" onClick={() => setPromptDraft({ id: "", name: "", content: "" })} type="button">取消编辑</button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className="settings-card" style={{ marginTop: 12 }}>
                    {userPrompts.map((prompt) => (
                      <div className="settings-card-row" key={prompt.id}>
                        <div className="settings-row-info">
                          <strong>{prompt.name}</strong>
                          <span>{prompt.content}</span>
                        </div>
                        <div className="settings-row-control" style={{ gap: 6 }}>
                          <button className="ghost-button" onClick={() => setPromptDraft({ id: prompt.id, name: prompt.name, content: prompt.content })} type="button">编辑</button>
                          <button className="ghost-button" onClick={() => void handleDeleteUserPrompt(prompt.id)} type="button">删除</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : null}

            {activeSection === "agent" ? (
              <div className="settings-section">
                <div className="settings-section-header">
                  <h3>Agent 配置</h3>
                  <p>官方 Skills 与企业 Skills 只读展示，执行配置由后端统一管理</p>
                </div>
                <div className="settings-card">
                  {skills.map((skill) => (
                    <div className="settings-card-row" key={skill.name}>
                      <div className="settings-row-info">
                        <strong>{skill.display_name}</strong>
                        <span>{skill.name} · {skill.category || "未分类"} · {skill.priority}</span>
                      </div>
                    </div>
                  ))}
                  {skills.length === 0 ? (
                    <div className="settings-card-row">
                      <span className="meta">暂无可用 Skill。</span>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}

            {activeSection === "remote" ? (
              <div className="settings-section">
                <div className="settings-section-header">
                  <h3>远程连接</h3>
                  <p>钉钉 Bot 等企业集成配置</p>
                </div>
                <div className="settings-card">
                  <div className="settings-card-row">
                    <div className="settings-row-info">
                      <strong>钉钉 Webhook</strong>
                    </div>
                    <div className="settings-row-control">
                      <input
                        value={preferences.dingTalkWebhook}
                        onChange={(event) => updatePreference({ dingTalkWebhook: event.target.value })}
                        style={{ minWidth: 260, height: 34, padding: "0 10px", border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--background))", color: "hsl(var(--foreground))", fontSize: 13 }}
                      />
                    </div>
                  </div>
                  <div className="settings-card-row">
                    <div className="settings-row-info">
                      <strong>钉钉 Token</strong>
                    </div>
                    <div className="settings-row-control">
                      <input
                        value={preferences.dingTalkToken}
                        onChange={(event) => updatePreference({ dingTalkToken: event.target.value })}
                        style={{ minWidth: 260, height: 34, padding: "0 10px", border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--background))", color: "hsl(var(--foreground))", fontSize: 13 }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {activeSection === "tutorial" ? (
              <div className="settings-section">
                <div className="settings-section-header">
                  <h3>软件教程</h3>
                  <p>快速上手指南</p>
                </div>
                <div className="settings-card">
                  <div className="settings-card-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
                    <strong>开始工作</strong>
                      <span>创建或选择项目，在 Chat 中提问，在 Agent 中查看项目文件。</span>
                  </div>
                  <div className="settings-card-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
                    <strong>知识库问答</strong>
                    <span>使用普通提问或 <code>/query</code> 固定知识库模式，回答会显示来源。</span>
                  </div>
                  <div className="settings-card-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
                    <strong>业务 Skill</strong>
                    <span>例如选择"项目沟通风险分析"，系统会按业务 Skill 的结构输出分析结果。</span>
                  </div>
                </div>
              </div>
            ) : null}

            {activeSection === "shortcuts" ? (
              <div className="settings-section">
                <div className="settings-section-header">
                  <h3>快捷键管理</h3>
                  <p>自定义键盘快捷操作</p>
                </div>
                <div className="settings-card">
                  {[
                    ["newChat", "新建对话"],
                    ["search", "搜索对话"],
                    ["settings", "打开设置"],
                    ["send", "发送消息"],
                    ["newline", "换行"],
                  ].map(([key, label]) => (
                    <div className="settings-card-row" key={key}>
                      <div className="settings-row-info">
                        <strong>{label}</strong>
                      </div>
                      <div className="settings-row-control">
                        <input
                          value={preferences.shortcuts?.[key] ?? DEFAULT_SHORTCUTS[key]}
                          onChange={(event) => updatePreference({
                            shortcuts: { ...(preferences.shortcuts ?? DEFAULT_SHORTCUTS), [key]: event.target.value },
                          })}
                          style={{ width: 140, height: 34, padding: "0 10px", border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--background))", color: "hsl(var(--foreground))", fontSize: 13, textAlign: "right" }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {activeSection === "admin" && currentUser?.role === "admin" ? (
              <>
                <div className="settings-section">
                  <div className="settings-section-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div>
                      <h3>管理员后台</h3>
                      <p>系统管理与监控</p>
                    </div>
                    <button className="ghost-button" onClick={() => void loadAdminData()} type="button">
                      刷新
                    </button>
                  </div>
                  {adminMessage ? <p className="connection-status connection-status-idle" style={{ marginBottom: 12 }}>{adminMessage}</p> : null}
                  {adminLoading ? <p className="meta">正在加载管理员数据...</p> : null}
                </div>

                <div className="admin-sub-tabs">
                  {([
                    { id: "overview", label: "概览" },
                    { id: "users", label: "用户管理" },
                    { id: "reviews", label: "知识审核", badge: knowledgeReviews.length },
                    { id: "gbrain", label: "GBrain 维护" },
                    { id: "templates", label: "模板 / Skill" },
                    { id: "updates", label: "客户端更新" },
                    { id: "audit", label: "审计日志" },
                  ] as Array<{ id: AdminTab; label: string; badge?: number }>).map((tab) => (
                    <button
                      key={tab.id}
                      className={`admin-sub-tab ${adminTab === tab.id ? "is-active" : ""}`}
                      onClick={() => setAdminTab(tab.id)}
                      type="button"
                    >
                      {tab.label}
                      {tab.badge ? <span className="admin-sub-tab-badge">{tab.badge}</span> : null}
                    </button>
                  ))}
                </div>

                {adminTab === "overview" ? (
                  <>
                    <div className="settings-section">
                      <div className="settings-section-header">
                        <h3>系统概览</h3>
                      </div>
                      <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                        <div className="metric-card-clickable" onClick={() => setAdminTab("users")} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setAdminTab("users"); }}>
                          <strong>{adminUsers.length}</strong>
                          <span>总用户数</span>
                        </div>
                        <div className="metric-card-clickable" onClick={() => setAdminTab("reviews")} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setAdminTab("reviews"); }}>
                          <strong>{knowledgeReviews.length}</strong>
                          <span>待审核知识</span>
                        </div>
                        <div className="metric-card-clickable" onClick={() => setAdminTab("audit")} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setAdminTab("audit"); }}>
                          <strong>{auditLogs.length}</strong>
                          <span>近期审计</span>
                        </div>
                        <div className="metric-card-clickable" onClick={() => setAdminTab("updates")} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setAdminTab("updates"); }}>
                          <strong>{updateReleases.length}</strong>
                          <span>客户端版本</span>
                        </div>
                      </div>
                    </div>

                    <div className="settings-section">
                      <div className="settings-section-header">
                        <h3>GBrain 知识库</h3>
                        <p>company-wiki source 与本机 embedding 状态</p>
                      </div>
                      <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                        <div>
                          <strong>{statusLabel(knowledgeStatus?.service?.status)}</strong>
                          <span>HTTP 服务</span>
                        </div>
                        <div>
                          <strong>{statusLabel(knowledgeStatus?.source?.status)}</strong>
                          <span>source 注册</span>
                        </div>
                        <div>
                          <strong>{yesNo(knowledgeStatus?.semantic_search_ready)}</strong>
                          <span>语义检索</span>
                        </div>
                        <div>
                          <strong>{knowledgeStatus?.page_count ?? knowledgeStatus?.indexed_files ?? "-"}</strong>
                          <span>页面</span>
                        </div>
                        <div>
                          <strong>{knowledgeStatus?.chunk_count ?? knowledgeStatus?.indexed_chunks ?? "-"}</strong>
                          <span>片段</span>
                        </div>
                        <div>
                          <strong>{knowledgeStatus?.embedding?.model ?? knowledgeStatus?.embedding_model ?? "-"}</strong>
                          <span>嵌入模型</span>
                        </div>
                        <div>
                          <strong>{knowledgeStatus?.ingest?.summary?.compiled ?? "-"}</strong>
                          <span>最近编译</span>
                        </div>
                        <div>
                          <strong>{knowledgeStatus?.doctor?.health_score ?? "-"}</strong>
                          <span>doctor 分数</span>
                        </div>
                      </div>
                      {knowledgeStatus?.readiness?.errors?.length ? (
                        <div className="admin-list" style={{ marginBottom: 12 }}>
                          {knowledgeStatus.readiness.errors.map((item) => (
                            <div className="admin-row" key={item}>
                              <div>
                                <strong>待处理</strong>
                                <span>{item}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {knowledgeStatus?.doctor?.warning_or_failed_checks?.length ? (
                        <div className="admin-list" style={{ marginBottom: 12 }}>
                          {knowledgeStatus.doctor.warning_or_failed_checks.map((item) => (
                            <div className="admin-row" key={`${item.name}-${item.message}`}>
                              <div>
                                <strong>{item.name ?? "doctor"}</strong>
                                <span>{statusLabel(item.status)} · {item.message}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                      {(() => {
                        const latest = knowledgeStatus?.quality_reports?.latest;
                        const summary = latest?.summary;
                        const trend = knowledgeStatus?.quality_reports?.trend ?? [];
                        return (
                          <div className="admin-list" style={{ marginBottom: 12 }}>
                            <div className="admin-row">
                              <div>
                                <strong>最近质量报告</strong>
                                <span>
                                  {latest
                                    ? [
                                        `query ${summary?.query?.passed ?? latest.query?.passed ?? 0}/${summary?.query?.total ?? latest.query?.total ?? 0}`,
                                        `think ${summary?.think?.passed ?? latest.think?.passed ?? 0}/${summary?.think?.total ?? latest.think?.total ?? 0}`,
                                        latest.ok ? "通过" : "有失败",
                                        latest.ran_at ? formatDate(latest.ran_at) : null,
                                      ].filter(Boolean).join(" · ")
                                    : "尚未生成质量报告"}
                                </span>
                              </div>
                              {latest?.id ? (
                                <button className="ghost-button" disabled={adminLoading} onClick={() => void handleExportKnowledgeQualityReport(latest.id)} type="button">
                                  导出
                                </button>
                              ) : null}
                            </div>
                            {summary?.failed_cases?.length ? (
                              <div className="admin-row">
                                <div>
                                  <strong>失败用例</strong>
                                  <span>{summary.failed_cases.slice(0, 6).join("、")}</span>
                                </div>
                              </div>
                            ) : null}
                            {summary?.preflight_failures?.length ? (
                              <div className="admin-row">
                                <div>
                                  <strong>预检失败</strong>
                                  <span>{summary.preflight_failures.slice(0, 4).join("；")}</span>
                                </div>
                              </div>
                            ) : null}
                            {trend.length ? (
                              <div className="admin-row">
                                <div>
                                  <strong>质量趋势</strong>
                                  <span>
                                    {trend.slice(0, 5).map((item) => {
                                      const queryRate =
                                        typeof item.query_pass_rate === "number" ? `${Math.round(item.query_pass_rate * 100)}%` : "n/a";
                                      const thinkRate =
                                        typeof item.think_pass_rate === "number" ? `${Math.round(item.think_pass_rate * 100)}%` : "n/a";
                                      const failed = (item.query_failed ?? 0) + (item.think_failed ?? 0);
                                      return `${item.ran_at ? formatDate(item.ran_at) : item.id ?? "report"}：Q ${queryRate} / T ${thinkRate}${failed ? ` / 失败 ${failed}` : ""}`;
                                    }).join("；")}
                                  </span>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })()}
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
                        <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRunKnowledgeQualityReport(false)} type="button">
                          查询质量报告
                        </button>
                        <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRunKnowledgeQualityReport(true)} type="button">
                          Think 质量报告
                        </button>
                        <button className="ghost-button" disabled={adminLoading || !knowledgeStatus?.quality_reports?.latest?.id} onClick={() => void handleExportKnowledgeQualityReport()} type="button">
                          导出报告
                        </button>
                        <button className="ghost-button" onClick={() => void handleStartGBrain()} type="button">
                          启动 GBrain
                        </button>
                        <button className="ghost-button" onClick={() => void handleRestartGBrain()} type="button">
                          重启 GBrain
                        </button>
                        <button className="ghost-button" onClick={() => void handleRefreshKnowledge()} type="button">
                          导入 raw 并同步
                        </button>
                        <button className="ghost-button" onClick={() => void handleRefreshKnowledge(true)} type="button">
                          含 PDF 提炼
                        </button>
                      </div>
                    </div>
                  </>
                ) : null}

                {adminTab === "users" ? (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3>用户管理</h3>
                      <p>这里设置的是系统角色；项目管理员由项目成员身份判断，创建或导入项目的人默认是该项目管理员。</p>
                    </div>
                    <div className="admin-toolbar">
                      <AdminComboInput
                        className="admin-search-combo"
                        icon={<SearchIcon />}
                        options={adminUserSearchOptions}
                        placeholder="搜索用户名或昵称"
                        value={userSearch}
                        onChange={(value) => { setUserSearch(value); setUserPage(1); }}
                        onSelect={(value) => { setUserSearch(value); setUserPage(1); }}
                      />
                      <button className="ghost-button" onClick={() => setShowCreateUser((prev) => !prev)} type="button">
                        {showCreateUser ? "取消" : "新增用户"}
                      </button>
                    </div>
                    {showCreateUser ? (
                      <div className="admin-create-user" style={{ marginBottom: 12 }}>
                        <input placeholder="用户名" value={newUser.username} onChange={(event) => setNewUser((prev) => ({ ...prev, username: event.target.value }))} />
                        <input placeholder="昵称" value={newUser.nickname} onChange={(event) => setNewUser((prev) => ({ ...prev, nickname: event.target.value }))} />
                        <input placeholder="初始密码" type="password" value={newUser.password} onChange={(event) => setNewUser((prev) => ({ ...prev, password: event.target.value }))} />
                        <AdminComboInput
                          options={adminGroupOptions}
                          placeholder="组别"
                          value={newUser.work_group}
                          onChange={(value) => setNewUser((prev) => ({ ...prev, work_group: value }))}
                          onSelect={(value) => setNewUser((prev) => ({ ...prev, work_group: value }))}
                        />
                        <select value={newUser.role} onChange={(event) => setNewUser((prev) => ({ ...prev, role: event.target.value }))}>
                          <option value="employee">员工</option>
                          <option value="admin">管理员</option>
                        </select>
                        <button onClick={() => void handleCreateUser().then(() => setShowCreateUser(false))} type="button">新增</button>
                      </div>
                    ) : null}
                    {(() => {
                      const filtered = sortUsers(filterUsers(adminUsers, userSearch), userSort);
                      const pageSize = 15;
                      const paged = paginate(filtered, userPage, pageSize);
                      const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
                      return (
                        <>
                          <div className="admin-table">
                            <div className="admin-table-header admin-users-table-grid">
                              <span className="sortable" onClick={() => setUserSort((prev) => ({ field: "username", dir: prev.field === "username" && prev.dir === "asc" ? "desc" : "asc" }))}>
                                用户名 {userSort.field === "username" ? (userSort.dir === "asc" ? "↑" : "↓") : ""}
                              </span>
                              <span>昵称</span>
                              <span>角色</span>
                              <span>组别</span>
                              <span>状态</span>
                              <span style={{ textAlign: "right" }}>操作</span>
                            </div>
                            {paged.map((item) => (
                              <div className={`admin-table-row admin-users-table-grid ${item.is_active ? "" : "is-disabled-user"}`} key={item.id}>
                                <div className="admin-table-cell">
                                  <div className="admin-user-identity">
                                    <strong>{item.username}</strong>
                                    <span>#{item.id}{isSystemAccount(item) ? " · 固定内置管理员" : ""}</span>
                                  </div>
                                </div>
                                <div className="admin-table-cell">{item.nickname || "-"}</div>
                                <div className="admin-table-cell">
                                  <label className={`admin-role-select ${item.role === "admin" ? "is-admin" : ""}`}>
                                    {item.role === "admin" ? <ShieldIcon /> : null}
                                    <select
                                      aria-label={`修改 ${item.username} 的角色`}
                                      disabled={isSystemAccount(item)}
                                      value={item.role === "admin" ? "admin" : "employee"}
                                      onChange={(event) => requestRoleChange(item, event.target.value as AdminUserRole)}
                                    >
                                      <option value="employee">员工</option>
                                      <option value="admin">管理员</option>
                                    </select>
                                    <ChevronDownIcon />
                                  </label>
                                </div>
                                <div className="admin-table-cell">
                                  <AdminComboInput
                                    className="admin-group-cell-combo"
                                    disabled={isSystemAccount(item)}
                                    options={adminGroupOptions}
                                    placeholder="未分组"
                                    value={userGroupDrafts[item.id] ?? item.work_group ?? ""}
                                    onChange={(value) => setUserGroupDrafts((prev) => ({ ...prev, [item.id]: value }))}
                                    onSelect={(value) => void handleSaveUserGroup(item, value)}
                                    onCommit={(value) => void handleSaveUserGroup(item, value)}
                                  />
                                </div>
                                <div className="admin-table-cell">
                                  <span className={`admin-status-badge ${item.is_active ? "is-active" : "is-inactive"}`}>
                                    <span className="admin-status-dot" />
                                    {item.is_active ? "正常" : "已停用"}
                                  </span>
                                </div>
                                <div className="admin-table-cell-actions admin-user-actions">
                                  <button className="admin-edit-button" disabled={isSystemAccount(item)} onClick={() => openEditUser(item)} type="button">
                                    <EditIcon />
                                    编辑
                                  </button>
                                  <div className="admin-more-wrap">
                                    <button
                                      aria-expanded={openUserMenuId === item.id}
                                      aria-label={`${item.username} 更多操作`}
                                      className="admin-icon-button"
                                      onClick={() => setOpenUserMenuId((current) => (current === item.id ? null : item.id))}
                                      type="button"
                                    >
                                      <MoreIcon />
                                    </button>
                                    {openUserMenuId === item.id ? (
                                      <>
                                        <div className="admin-action-menu-backdrop" onClick={() => setOpenUserMenuId(null)} />
                                        <div className="admin-action-menu">
                                          <button disabled={isSystemAccount(item)} onClick={() => openPasswordDialog(item)} type="button">
                                            重置密码
                                          </button>
                                          <button
                                            disabled={isSystemAccount(item) || (currentUser?.user_id === item.id && item.is_active)}
                                            onClick={() => requestStatusChange(item, !item.is_active)}
                                            type="button"
                                          >
                                            {item.is_active ? "停用账号" : "启用账号"}
                                          </button>
                                          <button
                                            className="admin-action-danger"
                                            disabled={isSystemAccount(item) || currentUser?.user_id === item.id}
                                            onClick={() => requestDeleteUser(item)}
                                            type="button"
                                          >
                                            删除账号
                                          </button>
                                        </div>
                                      </>
                                    ) : null}
                                  </div>
                                </div>
                              </div>
                            ))}
                            {paged.length === 0 ? (
                              <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>无匹配用户</div>
                            ) : null}
                          </div>
                          {totalPages > 1 ? (
                            <div className="admin-pagination">
                              <button disabled={userPage <= 1} onClick={() => setUserPage((p) => Math.max(1, p - 1))} type="button">上一页</button>
                              <span className="page-info">第 {userPage} / {totalPages} 页</span>
                              <button disabled={userPage >= totalPages} onClick={() => setUserPage((p) => Math.min(totalPages, p + 1))} type="button">下一页</button>
                            </div>
                          ) : null}
                        </>
                      );
                    })()}
                  </div>
                ) : null}

                {adminTab === "reviews" ? (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3>知识审核</h3>
                    </div>
                    <div className="admin-toolbar">
                      <input
                        className="admin-search"
                        placeholder="搜索来源或内容"
                        value={reviewSearch}
                        onChange={(event) => { setReviewSearch(event.target.value); setReviewPage(1); }}
                      />
                    </div>
                    {(() => {
                      const filtered = filterReviews(knowledgeReviews, reviewSearch);
                      const pageSize = 10;
                      const paged = paginate(filtered, reviewPage, pageSize);
                      const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
                      return (
                        <>
                          {filtered.length === 0 ? (
                            <p className="meta">暂无待审核知识。</p>
                          ) : (
                            <div className="admin-table">
                              <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr) 140px 220px" }}>
                                <span>来源</span>
                                <span>内容</span>
                                <span>提交时间</span>
                                <span style={{ textAlign: "right" }}>操作</span>
                              </div>
                              {paged.map((item) => (
                                <div className="admin-table-row" key={item.id} style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr) 140px 220px" }}>
                                  <div className="admin-table-cell">{item.source || "候选知识"}</div>
                                  <div className="admin-table-cell" title={item.content}>{item.content}</div>
                                  <div className="admin-table-cell admin-table-cell-secondary">{formatDate(item.created_at)}</div>
                                  <div className="admin-table-cell-actions">
                                    {canSubmitReviewCitationFixer(item) ? (
                                      <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitReviewCitationFixer(item)} type="button">引用修复</button>
                                    ) : null}
                                    <button className="ghost-button" onClick={() => void handleReviewKnowledge(item, "approved")} type="button">通过</button>
                                    <button className="ghost-button" onClick={() => void handleReviewKnowledge(item, "rejected")} type="button">驳回</button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                          {totalPages > 1 ? (
                            <div className="admin-pagination">
                              <button disabled={reviewPage <= 1} onClick={() => setReviewPage((p) => Math.max(1, p - 1))} type="button">上一页</button>
                              <span className="page-info">第 {reviewPage} / {totalPages} 页</span>
                              <button disabled={reviewPage >= totalPages} onClick={() => setReviewPage((p) => Math.min(totalPages, p + 1))} type="button">下一页</button>
                            </div>
                          ) : null}
                        </>
                      );
                    })()}
                  </div>
                ) : null}

                {adminTab === "gbrain" ? (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <div>
                        <h3>GBrain 维护</h3>
                        <p>doctor、maintain check、jobs 与 contradiction 的管理员入口</p>
                      </div>
                    </div>
                    {(() => {
                      const doctorSummary = asRecord(gbrainMaintenance?.doctor_summary);
                      const agentStatus = asRecord(gbrainMaintenance?.agent);
                      const jobs = toolResultArray(gbrainMaintenance?.jobs);
                      const contradictions = toolResultArray(gbrainMaintenance?.contradictions, "contradictions");
                      const healthScore = recordNumber(doctorSummary, "health_score");
                      const citationFixerJobs = gbrainMaintenance?.citation_fixer_jobs?.tracked_jobs ?? [];
                      const citationFixerRecentJobs = citationFixerJobs.slice(-5).reverse();
                      const maintenanceWorker = gbrainMaintenance?.dream_cycle_worker;
                      const workerTick = asRecord(maintenanceWorker?.last_tick_result);
                      const workerPoll = asRecord(maintenanceWorker?.last_poll_result);
                      const citationWorkerPoll = asRecord(maintenanceWorker?.last_citation_fixer_poll_result);
                      const contradictionProbe = gbrainMaintenance?.contradiction_probe;
                      const contradictionSummary = asRecord(contradictionProbe?.last_summary);
                      const contradictionWorkerProbe = asRecord(maintenanceWorker?.last_contradiction_probe_result);
                      const workerError = maintenanceWorker?.last_error?.trim() ?? "";
                      const graphNodeTitleById = new Map((gbrainGraph?.nodes ?? []).map((node) => [node.id, node.title]));
                      const graphNodes = (gbrainGraph?.nodes ?? []).slice(0, 12);
                      const graphEdges = (gbrainGraph?.edges ?? []).slice(0, 12);
                      const graphEvents = (gbrainGraph?.events ?? []).slice(0, 8);
                      const entityMergeCandidates = (gbrainEntityMerge?.candidates ?? []).slice(0, 12);
                      return (
                        <>
                          <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                            <div>
                              <strong>{gbrainMaintenance?.ok ? "正常" : "需检查"}</strong>
                              <span>维护状态</span>
                            </div>
                            <div>
                              <strong>{healthScore ?? "-"}</strong>
                              <span>doctor 分数</span>
                            </div>
                            <div>
                              <strong>{toolStatus(gbrainMaintenance?.jobs)}</strong>
                              <span>jobs 接口</span>
                            </div>
                            <div>
                              <strong>{jobs.length}</strong>
                              <span>最近任务</span>
                            </div>
                            <div>
                              <strong>{toolStatus(gbrainMaintenance?.contradictions)}</strong>
                              <span>冲突检测</span>
                            </div>
                            <div>
                              <strong>{contradictions.length}</strong>
                              <span>冲突记录</span>
                            </div>
                            <div>
                              <strong>{toolStatus(gbrainMaintenance?.onboard_check)}</strong>
                              <span>maintain check</span>
                            </div>
                            <div>
                              <strong>{statusLabel(recordText(agentStatus, "status"))}</strong>
                              <span>agent OAuth</span>
                            </div>
                            <div>
                              <strong>{gbrainMaintenance?.ran_at ? formatDate(gbrainMaintenance.ran_at) : "-"}</strong>
                              <span>更新时间</span>
                            </div>
                          </div>

                          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRefreshGBrainMaintenance()} type="button">
                              刷新状态
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleGBrainMaintenanceCheck()} type="button">
                              维护检查
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("sync")} type="button">
                              提交 sync
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("embed")} type="button">
                              提交 embed
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("lint")} type="button">
                              lint 预检
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("backlinks")} type="button">
                              backlinks 检查
                            </button>
                          </div>

                          <div className="admin-maintenance-form" style={{ gridTemplateColumns: "92px 92px 92px minmax(120px, 1fr) minmax(150px, 1.2fr) auto auto auto auto auto" }}>
                            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "hsl(var(--muted-foreground))" }}>
                              <input
                                checked={gbrainDreamDraft.enabled}
                                onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, enabled: event.target.checked }))}
                                type="checkbox"
                              />
                              启用
                            </label>
                            <input
                              inputMode="numeric"
                              placeholder="间隔小时"
                              value={gbrainDreamDraft.intervalHours}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, intervalHours: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="目标分"
                              value={gbrainDreamDraft.targetScore}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, targetScore: event.target.value }))}
                            />
                            <input
                              placeholder="source id"
                              value={gbrainDreamDraft.sourceId}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, sourceId: event.target.value }))}
                            />
                            <input
                              placeholder="jobs，逗号分隔"
                              value={gbrainDreamDraft.jobNames}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, jobNames: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSaveGBrainDreamCycle()} type="button">
                              保存 Dream
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRunGBrainDreamCycle()} type="button">
                              立即运行
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleTickGBrainDreamCycle()} type="button">
                              检查到期
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handlePollGBrainDreamCycleJobs()} type="button">
                              轮询任务
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRestartGBrainDreamCycleWorker()} type="button">
                              重启 Worker
                            </button>
                          </div>

                          <div className="admin-list" style={{ marginBottom: 12 }}>
                            <div className="admin-row">
                              <div>
                                <strong>Dream Cycle</strong>
                                <span>
                                  {`状态 ${gbrainMaintenance?.dream_cycle?.enabled ? "启用" : "停用"} · 上次 ${gbrainMaintenance?.dream_cycle?.last_run_at ? formatDate(gbrainMaintenance.dream_cycle.last_run_at) : "-"} · 下次 ${gbrainMaintenance?.dream_cycle?.next_run_at ? formatDate(gbrainMaintenance.dream_cycle.next_run_at) : "-"} · 跟踪任务 ${gbrainMaintenance?.dream_cycle?.tracked_jobs?.length ?? 0} · 最近轮询 ${gbrainMaintenance?.dream_cycle?.last_job_poll_at ? formatDate(gbrainMaintenance.dream_cycle.last_job_poll_at) : "-"} · Worker ${maintenanceWorker?.running ? "运行中" : "未运行"} · 心跳 ${maintenanceWorker?.last_heartbeat_at ? formatDate(maintenanceWorker.last_heartbeat_at) : "-"}`}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className={`admin-maintenance-card ${workerError ? "is-warning" : ""}`}>
                            <div>
                              <strong>GBrain Worker</strong>
                              <span>
                                {`状态 ${maintenanceWorker?.running ? "运行中" : "未运行"} · 配置 ${maintenanceWorker?.enabled ? "启用" : "停用"} · 间隔 ${maintenanceWorker?.interval_seconds ?? "-"}s · 次数 ${maintenanceWorker?.run_count ?? 0} · 心跳 ${formatOptionalDate(maintenanceWorker?.last_heartbeat_at)}`}
                              </span>
                            </div>
                            {workerError ? <p>{`最近错误：${workerError}`}</p> : <p>最近错误：无</p>}
                            <p>
                              {[
                                `Dream tick ${recordText(workerTick, "status") || "-"}`,
                                `Dream poll ${recordText(workerPoll, "status") || "-"} / ${shortValue(recordNumber(workerPoll, "checked"))}`,
                                `citation-fixer ${recordText(citationWorkerPoll, "status") || "-"} / ${shortValue(recordNumber(citationWorkerPoll, "checked"))}`,
                                `contradiction ${recordText(contradictionWorkerProbe, "status") || "-"}${recordText(contradictionWorkerProbe, "ran") ? ` / ran=${recordText(contradictionWorkerProbe, "ran")}` : ""}`,
                              ].join(" · ")}
                            </p>
                          </div>

                          <div className="admin-maintenance-form" style={{ gridTemplateColumns: "92px 92px minmax(120px, 1fr) 76px 88px 96px 96px auto auto auto" }}>
                            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "hsl(var(--muted-foreground))" }}>
                              <input
                                checked={gbrainContradictionDraft.enabled}
                                onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, enabled: event.target.checked }))}
                                type="checkbox"
                              />
                              冲突探针
                            </label>
                            <input
                              inputMode="numeric"
                              placeholder="间隔小时"
                              value={gbrainContradictionDraft.intervalHours}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, intervalHours: event.target.value }))}
                            />
                            <input
                              placeholder="source id"
                              value={gbrainContradictionDraft.sourceId}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, sourceId: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="topK"
                              value={gbrainContradictionDraft.topK}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, topK: event.target.value }))}
                            />
                            <input
                              inputMode="decimal"
                              placeholder="预算"
                              value={gbrainContradictionDraft.budgetUsd}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, budgetUsd: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="timeout"
                              value={gbrainContradictionDraft.timeoutSeconds}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, timeoutSeconds: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="结果数"
                              value={gbrainContradictionDraft.resultLimit}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, resultLimit: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSaveGBrainContradictionProbe()} type="button">
                              保存探针
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRunGBrainContradictionProbe()} type="button">
                              立即运行
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleTickGBrainContradictionProbe()} type="button">
                              检查到期
                            </button>
                            <textarea
                              placeholder="每行一个 probe 查询"
                              style={{ gridColumn: "1 / -1" }}
                              value={gbrainContradictionDraft.queries}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, queries: event.target.value }))}
                            />
                          </div>

                          <div className="admin-list" style={{ marginBottom: 12 }}>
                            <div className="admin-row">
                              <div>
                                <strong>Contradiction Probe</strong>
                                <span>
                                  {`状态 ${contradictionProbe?.enabled ? "启用" : "停用"} · 上次 ${formatOptionalDate(contradictionProbe?.last_run_at)} · 下次 ${formatOptionalDate(contradictionProbe?.next_run_at)} · 查询 ${contradictionProbe?.queries?.length ?? 0} · 疑似冲突 ${shortValue(recordNumber(contradictionSummary, "total_contradictions_flagged"))} · Worker ${recordText(contradictionWorkerProbe, "status") || "-"}`}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="admin-maintenance-form" style={{ gridTemplateColumns: "minmax(150px, 1fr) minmax(150px, 1fr) minmax(120px, 0.8fr) auto auto" }}>
                            <input
                              placeholder="source id"
                              value={gbrainGraphDraft.sourceId}
                              onChange={(event) => setGBrainGraphDraft((prev) => ({ ...prev, sourceId: event.target.value }))}
                            />
                            <input
                              placeholder="关注实体，如 5Points"
                              value={gbrainGraphDraft.focus}
                              onChange={(event) => setGBrainGraphDraft((prev) => ({ ...prev, focus: event.target.value }))}
                            />
                            <input
                              placeholder="实体类型，可空"
                              value={gbrainGraphDraft.entityType}
                              onChange={(event) => setGBrainGraphDraft((prev) => ({ ...prev, entityType: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleLoadGBrainGraph()} type="button">
                              加载图谱
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleLoadGBrainEntityMergeCandidates()} type="button">
                              实体候选
                            </button>
                          </div>

                          {gbrainGraph ? (
                            <>
                              <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                                <div>
                                  <strong>{gbrainGraph.source_id}</strong>
                                  <span>source</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.focus || "-"}</strong>
                                  <span>关注实体</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.stats?.nodes ?? gbrainGraph.nodes.length}</strong>
                                  <span>节点</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.stats?.edges ?? gbrainGraph.edges.length}</strong>
                                  <span>关系</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.stats?.events ?? gbrainGraph.events.length}</strong>
                                  <span>事件</span>
                                </div>
                              </div>

                              <div className="admin-table" style={{ marginBottom: 12 }}>
                                <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1.2fr) 120px minmax(0, 1.4fr)" }}>
                                  <span>实体</span>
                                  <span>类型</span>
                                  <span>引用</span>
                                </div>
                                {graphNodes.map((node) => (
                                  <div className="admin-table-row" key={node.id} style={{ gridTemplateColumns: "minmax(0, 1.2fr) 120px minmax(0, 1.4fr)" }}>
                                    <div className="admin-table-cell" title={node.id}>{node.title}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary">{node.entity_type}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary" title={node.source_file || node.file}>{node.source_file || node.file}</div>
                                  </div>
                                ))}
                                {graphNodes.length === 0 ? (
                                  <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无图谱实体</div>
                                ) : null}
                              </div>

                              <div className="admin-table" style={{ marginBottom: 12 }}>
                                <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1fr) 120px minmax(0, 1fr) minmax(0, 1.2fr)" }}>
                                  <span>起点</span>
                                  <span>关系</span>
                                  <span>终点</span>
                                  <span>证据</span>
                                </div>
                                {graphEdges.map((edge) => (
                                  <div className="admin-table-row" key={edge.id} style={{ gridTemplateColumns: "minmax(0, 1fr) 120px minmax(0, 1fr) minmax(0, 1.2fr)" }}>
                                    <div className="admin-table-cell" title={edge.from}>{graphNodeTitleById.get(edge.from) || edge.from}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary">{edge.relation_type}</div>
                                    <div className="admin-table-cell" title={edge.to}>{graphNodeTitleById.get(edge.to) || edge.to}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary" title={edge.evidence || ""}>{edge.evidence || "-"}</div>
                                  </div>
                                ))}
                                {graphEdges.length === 0 ? (
                                  <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无图谱关系</div>
                                ) : null}
                              </div>

                              <div className="admin-list" style={{ marginBottom: 12 }}>
                                {graphEvents.map((event) => (
                                  <div className="admin-row" key={event.id}>
                                    <div>
                                      <strong>{event.title}</strong>
                                      <span>{[event.date, graphNodeTitleById.get(event.entity_id) || event.entity_id, event.source_file].filter(Boolean).join(" · ")}</span>
                                    </div>
                                  </div>
                                ))}
                                {graphEvents.length === 0 ? (
                                  <div className="admin-row">
                                    <div>
                                      <strong>暂无事件</strong>
                                      <span>{gbrainGraph.warnings?.[0] || "当前过滤条件下没有 source event。"}</span>
                                    </div>
                                  </div>
                                ) : null}
                              </div>
                            </>
                          ) : null}

                          {gbrainEntityMerge ? (
                            <>
                              <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                                <div>
                                  <strong>{gbrainEntityMerge.source_id}</strong>
                                  <span>候选 source</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.focus || "-"}</strong>
                                  <span>筛选实体</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.stats?.candidates ?? gbrainEntityMerge.candidates.length}</strong>
                                  <span>候选</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.stats?.unresolved ?? "-"}</strong>
                                  <span>未解析</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.stats?.duplicates ?? "-"}</strong>
                                  <span>重复页面</span>
                                </div>
                              </div>

                              <div className="admin-table" style={{ marginBottom: 12 }}>
                                <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1fr) 130px 130px minmax(0, 1.2fr) 132px" }}>
                                  <span>候选实体</span>
                                  <span>类型</span>
                                  <span>建议动作</span>
                                  <span>证据 / 目标</span>
                                  <span style={{ textAlign: "right" }}>操作</span>
                                </div>
                                {entityMergeCandidates.map((candidate) => {
                                  const targets = (candidate.target_nodes ?? []).map((node) => node.title).filter(Boolean).join(", ");
                                  const evidence = (candidate.evidence_edges ?? []).map((edge) => edge.evidence).filter(Boolean).join(", ");
                                  const canCreate = candidate.suggested_action === "create_entity_page" || candidate.suggested_action === "create_event_page";
                                  const canRecordAlias = candidate.suggested_action === "merge_duplicate_pages" || candidate.suggested_action === "link_to_existing_entity";
                                  return (
                                    <div className="admin-table-row" key={candidate.id} style={{ gridTemplateColumns: "minmax(0, 1fr) 130px 130px minmax(0, 1.2fr) 180px" }}>
                                      <div className="admin-table-cell" title={candidate.id}>{candidate.title}</div>
                                      <div className="admin-table-cell admin-table-cell-secondary">{candidate.candidate_type}</div>
                                      <div className="admin-table-cell admin-table-cell-secondary">{candidate.suggested_action}</div>
                                      <div className="admin-table-cell admin-table-cell-secondary" title={candidate.reason || ""}>
                                        {targets || evidence || candidate.reason || "-"}
                                      </div>
                                      <div className="admin-table-cell-actions">
                                        <button className="ghost-button" disabled={adminLoading || !canCreate} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "create_entity_page")} type="button">
                                          创建
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading || !canRecordAlias} onClick={() => void handlePreviewGBrainEntityMergeCandidate(candidate)} type="button">
                                          预览
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading || !canRecordAlias} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "record_alias")} type="button">
                                          别名
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading || !canRecordAlias} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "apply_relink_changes")} type="button">
                                          改写
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "dismiss")} type="button">
                                          忽略
                                        </button>
                                      </div>
                                    </div>
                                  );
                                })}
                                {entityMergeCandidates.length === 0 ? (
                                  <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无实体合并候选</div>
                                ) : null}
                              </div>
                              {gbrainEntityMergePreview ? (
                                <div className="admin-maintenance-card">
                                  <div>
                                    <strong>实体合并预览</strong>
                                    <span>{gbrainEntityMergePreview.planned_alias_review_file || "未生成 alias 文件路径"}</span>
                                  </div>
                                  <p>
                                    主实体：{gbrainEntityMergePreview.canonical_entity?.title || "-"} · 别名：{(gbrainEntityMergePreview.alias_entities ?? []).map((node) => node.title).join(", ") || "-"}
                                  </p>
                                  {(gbrainEntityMergePreview.planned_relink_changes ?? []).slice(0, 6).map((change) => (
                                    <p key={`${change.page_id}-${change.field}-${change.index}`}>
                                      {change.page_title}: {change.diff_preview}
                                    </p>
                                  ))}
                                  {(gbrainEntityMergePreview.planned_relink_changes ?? []).length === 0 ? <p>未发现需要自动改写的 frontmatter 引用。</p> : null}
                                </div>
                              ) : null}
                            </>
                          ) : null}

                          <div className="admin-maintenance-form">
                            <input
                              placeholder="页面 slug"
                              value={citationFixerDraft.pageSlug}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, pageSlug: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="审核 ID"
                              value={citationFixerDraft.reviewId}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, reviewId: event.target.value }))}
                            />
                            <input
                              placeholder="slug 前缀，逗号分隔"
                              value={citationFixerDraft.slugPrefixes}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, slugPrefixes: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="turns"
                              value={citationFixerDraft.maxTurns}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, maxTurns: event.target.value }))}
                            />
                            <textarea
                              placeholder="备注"
                              value={citationFixerDraft.notes}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, notes: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitCitationFixer()} type="button">
                              提交 citation-fixer
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handlePollGBrainCitationFixerJobs()} type="button">
                              轮询引用修复
                            </button>
                          </div>

                          <div className="admin-list" style={{ marginBottom: 12 }}>
                            <div className="admin-row">
                              <div>
                                <strong>citation-fixer tracking</strong>
                                <span>
                                  {`跟踪任务 ${citationFixerJobs.length} · 最近轮询 ${formatOptionalDate(gbrainMaintenance?.citation_fixer_jobs?.last_job_poll_at)} · Worker 最近检查 ${shortValue(recordNumber(citationWorkerPoll, "checked"))} 个`}
                                </span>
                              </div>
                            </div>
                            {citationFixerRecentJobs.map((job) => {
                              const reconcile = asRecord(job.reconcile);
                              const git = asRecord(reconcile?.git);
                              const rollback = asRecord(job.rollback);
                              const canRollback = job.status === "completed" && Boolean(git?.commit_hash) && !rollback?.ok;
                              return (
                                <div className="admin-row" key={job.job_id}>
                                  <div>
                                    <strong>{`#${job.job_id} · ${statusLabel(job.status)}`}</strong>
                                    <span>
                                      {[
                                        job.page_slug || "-",
                                        job.source_id || "company-wiki",
                                        job.last_checked_at ? formatDate(job.last_checked_at) : "未轮询",
                                        rollback?.ok ? "已回滚" : null,
                                      ]
                                        .filter(Boolean)
                                        .join(" · ")}
                                    </span>
                                  </div>
                                  {canRollback ? (
                                    <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRollbackGBrainCitationFixerJob(job.job_id)} type="button">
                                      回滚
                                    </button>
                                  ) : null}
                                </div>
                              );
                            })}
                            {citationFixerJobs.length === 0 ? (
                              <div className="admin-row">
                                <div>
                                  <strong>暂无 citation-fixer 追踪任务</strong>
                                  <span>提交引用修复任务后会在这里显示 job 状态。</span>
                                </div>
                              </div>
                            ) : null}
                          </div>

                          <div className="admin-table" style={{ marginBottom: 12 }}>
                            <div className="admin-table-header" style={{ gridTemplateColumns: "70px minmax(0, 1fr) 96px minmax(0, 1.4fr) 140px" }}>
                              <span>ID</span>
                              <span>任务</span>
                              <span>状态</span>
                              <span>进度 / 错误</span>
                              <span style={{ textAlign: "right" }}>操作</span>
                            </div>
                            {jobs.map((job, index) => {
                              const jobId = recordNumber(job, "id");
                              const progress = shortValue(job.progress ?? job.error ?? job.result);
                              return (
                                <div className="admin-table-row" key={`${jobId ?? "job"}-${index}`} style={{ gridTemplateColumns: "70px minmax(0, 1fr) 96px minmax(0, 1.4fr) 140px" }}>
                                  <div className="admin-table-cell">#{jobId ?? "-"}</div>
                                  <div className="admin-table-cell">{recordText(job, "name") || "-"}</div>
                                  <div className="admin-table-cell">{statusLabel(recordText(job, "status"))}</div>
                                  <div className="admin-table-cell admin-table-cell-secondary" title={progress}>{progress}</div>
                                  <div className="admin-table-cell-actions">
                                    <button className="ghost-button" disabled={!jobId || adminLoading} onClick={() => jobId && void handleCancelGBrainJob(jobId)} type="button">取消</button>
                                    <button className="ghost-button" disabled={!jobId || adminLoading} onClick={() => jobId && void handleRetryGBrainJob(jobId)} type="button">重试</button>
                                  </div>
                                </div>
                              );
                            })}
                            {jobs.length === 0 ? (
                              <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无 GBrain 维护任务</div>
                            ) : null}
                          </div>

                          <div className="admin-list">
                            {contradictions.map((item, index) => (
                              <div className="admin-row" key={`${recordText(item, "severity")}-${index}`}>
                                <div>
                                  <strong>{recordText(item, "severity") || "contradiction"}</strong>
                                  <span>{recordText(item, "slug") || recordText(item, "left") || shortValue(item)}</span>
                                </div>
                              </div>
                            ))}
                            {contradictions.length === 0 ? (
                              <div className="admin-row">
                                <div>
                                  <strong>暂无冲突记录</strong>
                                  <span>{gbrainMaintenance?.contradictions?.status === "ok" ? "GBrain 当前没有可展示的 contradiction probe 结果。" : shortValue(gbrainMaintenance?.contradictions?.error)}</span>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                ) : null}

                {adminTab === "templates" ? (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3>模板 / Skill</h3>
                    </div>
                    <div className="admin-toolbar">
                      <input
                        className="admin-search"
                        placeholder="搜索名称或 Skill"
                        value={templateSearch}
                        onChange={(event) => setTemplateSearch(event.target.value)}
                      />
                    </div>
                    {(() => {
                      const filtered = filterTemplates(templates, templateSearch);
                      return (
                        <div className="admin-table">
                          <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr) minmax(0, 1fr)" }}>
                            <span>显示名称</span>
                            <span>Skill 名</span>
                            <span>输出格式</span>
                          </div>
                          {filtered.map((item) => (
                            <div className="admin-table-row" key={item.skill_name} style={{ gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr) minmax(0, 1fr)" }}>
                              <div className="admin-table-cell">{item.display_name}</div>
                              <div className="admin-table-cell admin-table-cell-secondary">{item.skill_name}</div>
                              <div className="admin-table-cell admin-table-cell-secondary">{item.outputs.map((output) => String(output.format ?? output.type ?? "output")).join(", ")}</div>
                            </div>
                          ))}
                          {filtered.length === 0 ? (
                            <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>无匹配模板</div>
                          ) : null}
                        </div>
                      );
                    })()}
                  </div>
                ) : null}

                {adminTab === "updates" ? (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3>客户端更新</h3>
                      <p>登记内网分发的 Windows 安装包，员工登录后按当前客户端版本检查更新。</p>
                    </div>
                    <div className="settings-card" style={{ marginBottom: 12 }}>
                      <div className="settings-card-row" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
                        <div className="admin-create-user" style={{ gridTemplateColumns: "minmax(100px, 1fr) minmax(100px, 1fr) 96px 120px" }}>
                          <input
                            placeholder="版本号，如 0.2.0"
                            value={updateDraft.version}
                            onChange={(event) => setUpdateDraft((prev) => ({ ...prev, version: event.target.value }))}
                          />
                          <input
                            placeholder="最低支持版本，可留空"
                            value={updateDraft.minimumSupportedVersion}
                            onChange={(event) => setUpdateDraft((prev) => ({ ...prev, minimumSupportedVersion: event.target.value }))}
                          />
                          <select
                            value={updateDraft.platform}
                            onChange={(event) => setUpdateDraft((prev) => ({ ...prev, platform: event.target.value }))}
                          >
                            <option value="win32">Windows</option>
                          </select>
                          <button className="ghost-button" onClick={() => updateFileInputRef.current?.click()} type="button">
                            选择安装包
                          </button>
                        </div>
                        <textarea
                          placeholder="更新日志，支持 Markdown 文本"
                          rows={5}
                          style={{ width: "100%", padding: 10, border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--background))", color: "hsl(var(--foreground))", resize: "vertical" }}
                          value={updateDraft.releaseNotes}
                          onChange={(event) => setUpdateDraft((prev) => ({ ...prev, releaseNotes: event.target.value }))}
                        />
                        <input
                          accept=".exe,.msi,.zip,.dmg,.pkg"
                          ref={updateFileInputRef}
                          style={{ display: "none" }}
                          type="file"
                          onChange={(event) => setUpdateFile(event.target.files?.[0] ?? null)}
                        />
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                              <input
                                checked={updateDraft.isForceUpdate}
                                onChange={(event) => setUpdateDraft((prev) => ({ ...prev, isForceUpdate: event.target.checked }))}
                                type="checkbox"
                              />
                              强制更新
                            </label>
                            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                              <input
                                checked={updateDraft.isActive}
                                onChange={(event) => setUpdateDraft((prev) => ({ ...prev, isActive: event.target.checked }))}
                                type="checkbox"
                              />
                              发布为可用版本
                            </label>
                            <span className="meta">{updateFile ? `${updateFile.name} · ${formatFileSize(updateFile.size)}` : "未选择安装包"}</span>
                          </div>
                          <button disabled={adminLoading || !updateDraft.version.trim() || !updateFile} onClick={() => void handleUploadUpdateRelease()} type="button">
                            上传并登记
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="admin-table">
                      <div className="admin-table-header" style={{ gridTemplateColumns: "100px 88px minmax(0, 1fr) 86px 86px 130px" }}>
                        <span>版本</span>
                        <span>平台</span>
                        <span>安装包</span>
                        <span>大小</span>
                        <span>策略</span>
                        <span>登记时间</span>
                      </div>
                      {updateReleases.map((item) => (
                        <div className="admin-table-row" key={`${item.platform}-${item.version}`} style={{ gridTemplateColumns: "100px 88px minmax(0, 1fr) 86px 86px 130px" }}>
                          <div className="admin-table-cell">{item.version}</div>
                          <div className="admin-table-cell admin-table-cell-secondary">{item.platform}</div>
                          <div className="admin-table-cell" title={`${item.filename}\nSHA256: ${item.sha256}`}>{item.filename}</div>
                          <div className="admin-table-cell admin-table-cell-secondary">{formatFileSize(item.size_bytes)}</div>
                          <div className="admin-table-cell admin-table-cell-secondary">{item.is_force_update ? "强制" : "普通"} / {item.is_active ? "启用" : "停用"}</div>
                          <div className="admin-table-cell admin-table-cell-secondary">{formatDate(item.created_at)}</div>
                        </div>
                      ))}
                      {updateReleases.length === 0 ? (
                        <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无更新包</div>
                      ) : null}
                    </div>
                  </div>
                ) : null}

                {adminTab === "audit" ? (
                  <div className="settings-section">
                    <div className="settings-section-header">
                      <h3>审计日志</h3>
                    </div>
                    <div className="admin-audit-filters" style={{ gridTemplateColumns: "minmax(80px, 1fr) minmax(100px, 1fr) minmax(120px, 1fr) minmax(120px, 1fr) auto" }}>
                      <input placeholder="用户 ID" value={auditFilter.userId} onChange={(event) => setAuditFilter((prev) => ({ ...prev, userId: event.target.value }))} />
                      <select value={auditActionType} onChange={(event) => setAuditActionType(event.target.value)} style={{ height: 32, border: "1px solid hsl(var(--border))", borderRadius: 8, background: "hsl(var(--card))", color: "hsl(var(--foreground))", padding: "0 9px", fontSize: 12 }}>
                        <option value="">全部操作</option>
                        {uniqueAuditActions.map((action) => (
                          <option key={action} value={action}>{action}</option>
                        ))}
                      </select>
                      <input type="date" value={auditFilter.dateFrom} onChange={(event) => setAuditFilter((prev) => ({ ...prev, dateFrom: event.target.value }))} />
                      <input type="date" value={auditFilter.dateTo} onChange={(event) => setAuditFilter((prev) => ({ ...prev, dateTo: event.target.value }))} />
                      <button className="ghost-button" onClick={() => { setAuditPage(1); void loadAdminData(); }} type="button">筛选</button>
                    </div>
                    <div className="admin-toolbar">
                      <input
                        className="admin-search"
                        placeholder="搜索操作或详情"
                        value={auditSearch}
                        onChange={(event) => { setAuditSearch(event.target.value); setAuditPage(1); }}
                      />
                    </div>
                    {(() => {
                      const filtered = filterAuditLogs(auditLogs, auditSearch, auditActionType);
                      const pageSize = 20;
                      const paged = paginate(filtered, auditPage, pageSize);
                      const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
                      return (
                        <>
                          <div className="admin-table">
                            <div className="admin-table-header" style={{ gridTemplateColumns: "140px 70px minmax(0, 1fr) 70px 80px" }}>
                              <span>时间</span>
                              <span>用户</span>
                              <span>操作</span>
                              <span>结果</span>
                              <span style={{ textAlign: "right" }}>Token</span>
                            </div>
                            {paged.map((item) => (
                              <div className="admin-table-row" key={item.id} style={{ gridTemplateColumns: "140px 70px minmax(0, 1fr) 70px 80px" }}>
                                <div className="admin-table-cell admin-table-cell-secondary">{formatDate(item.created_at)}</div>
                                <div className="admin-table-cell admin-table-cell-secondary">#{item.user_id}</div>
                                <div className="admin-table-cell">{item.action}</div>
                                <div className="admin-table-cell">{item.success ? "成功" : "失败"}</div>
                                <div className="admin-table-cell" style={{ textAlign: "right" }}>{item.token_cost ? <span className="admin-token">{item.token_cost}</span> : "-"}</div>
                              </div>
                            ))}
                            {paged.length === 0 ? (
                              <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>无匹配记录</div>
                            ) : null}
                          </div>
                          {totalPages > 1 ? (
                            <div className="admin-pagination">
                              <button disabled={auditPage <= 1} onClick={() => setAuditPage((p) => Math.max(1, p - 1))} type="button">上一页</button>
                              <span className="page-info">第 {auditPage} / {totalPages} 页</span>
                              <button disabled={auditPage >= totalPages} onClick={() => setAuditPage((p) => Math.min(totalPages, p + 1))} type="button">下一页</button>
                            </div>
                          ) : null}
                        </>
                      );
                    })()}
                  </div>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      </div>
      {editingUser ? (
        <div className="admin-drawer-overlay" onClick={(event) => { event.stopPropagation(); setEditingUser(null); }}>
          <aside className="admin-user-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="admin-user-drawer-header">
              <div>
                <p className="eyebrow">User profile</p>
                <h3>{userDisplayName(editingUser)}</h3>
              <span>{editingUser.username} · #{editingUser.id}</span>
            </div>
              <button className="settings-dialog-close" onClick={() => setEditingUser(null)} title="关闭" type="button">
                <XmarkIcon />
              </button>
            </div>
            <div className="admin-drawer-status-row">
              <span className={`admin-status-badge ${editingUser.is_active ? "is-active" : "is-inactive"}`}>
                <span className="admin-status-dot" />
                {editingUser.is_active ? "正常" : "已停用"}
              </span>
              {editingUser.role === "admin" ? (
                <span className="admin-role-tag is-admin">
                  <ShieldIcon />
                  管理员
                </span>
              ) : (
                <span className="admin-role-tag">员工</span>
              )}
            </div>
            <label className="admin-form-field">
              <span>昵称</span>
              <input
                disabled={isSystemAccount(editingUser)}
                value={editUserDraft.nickname}
                onChange={(event) => setEditUserDraft({ nickname: event.target.value })}
                placeholder="显示在系统中的姓名"
              />
            </label>
            <label className="admin-form-field">
              <span>系统角色</span>
              <div className="admin-drawer-select-wrap">
                <select
                  disabled={isSystemAccount(editingUser)}
                  value={editingUser.role === "admin" ? "admin" : "employee"}
                  onChange={(event) => requestRoleChange(editingUser, event.target.value as AdminUserRole)}
                >
                  <option value="employee">员工</option>
                  <option value="admin">管理员</option>
                </select>
                <ChevronDownIcon />
              </div>
            </label>
            <p className="admin-drawer-note">
              {isSystemAccount(editingUser)
                ? "sysadmin 是系统内置管理员账号，用户名、密码、角色、昵称、头像和启用状态均固定。"
                : "角色、停用和密码重置都会保留审计记录。停用账号不能登录，但历史文件、聊天和日志不会断链。"}
            </p>
            <div className="admin-drawer-footer">
              <button className="ghost-button" onClick={() => setEditingUser(null)} type="button">
                取消
              </button>
              <button disabled={isSystemAccount(editingUser)} onClick={() => void handleSaveEditingUser()} type="button">
                保存资料
              </button>
            </div>
          </aside>
        </div>
      ) : null}
      {adminConfirm ? (
        <div className="admin-confirm-backdrop" onClick={(event) => event.stopPropagation()}>
          <div className="admin-confirm-dialog">
            <p className="eyebrow">Confirm change</p>
            <h3>{adminConfirmTitle(adminConfirm)}</h3>
            <p>{adminConfirmText(adminConfirm)}</p>
            <div className="admin-confirm-actions">
              <button className="ghost-button" onClick={() => setAdminConfirm(null)} type="button">
                取消
              </button>
              <button
                className={adminConfirmIsDanger(adminConfirm) ? "admin-danger-button" : ""}
                onClick={() => void handleConfirmAdminAction()}
                type="button"
              >
                {adminConfirm.type === "delete" ? "删除" : "确认"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {passwordDialog ? (
        <div className="admin-confirm-backdrop" onClick={(event) => event.stopPropagation()}>
          <div className="admin-confirm-dialog admin-password-dialog">
            <p className="eyebrow">Reset password</p>
            <h3>重置 {userDisplayName(passwordDialog.user)} 的密码</h3>
            <p>确认后会立即替换该用户的登录密码。新密码只在关闭弹窗前显示一次。</p>
            <label className="admin-form-field">
              <span>新密码</span>
              <input
                readOnly={Boolean(passwordDialog.resultPassword)}
                value={passwordDialog.password}
                onChange={(event) => setPasswordDialog((prev) => (prev ? { ...prev, password: event.target.value, resultPassword: null, copied: false } : prev))}
              />
            </label>
            {passwordDialog.resultPassword ? (
              <div className="admin-password-result">
                <span>已重置，通知用户前请先复制保存。</span>
                <button className="ghost-button" onClick={() => void handleCopyResetPassword()} type="button">
                  <CopyIcon />
                  {passwordDialog.copied ? "已复制" : "复制密码"}
                </button>
              </div>
            ) : null}
            <div className="admin-confirm-actions">
              <button className="ghost-button" onClick={() => setPasswordDialog(null)} type="button">
                {passwordDialog.resultPassword ? "关闭" : "取消"}
              </button>
              {!passwordDialog.resultPassword ? (
                <button onClick={() => void handleConfirmPasswordReset()} type="button">
                  确认重置
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
