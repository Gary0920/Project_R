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
import { GeneralSection } from "./settings/GeneralSection";
import { AdminSettingsPanel } from "./settings/AdminSettingsPanel";
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

const CUSTOMER_INTELLIGENCE_SOURCE_ID = "customer-crm";

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
              <GeneralSection
                avatarPickerRef={avatarPickerRef}
                avatarRef={avatarRef}
                commonEmojis={COMMON_EMOJIS}
                currentUser={currentUser}
                fileInputRef={fileInputRef}
                formatOptionalDate={formatOptionalDate}
                handleAvatarImageUpload={handleAvatarImageUpload}
                handleSelectEmoji={handleSelectEmoji}
                isEditingName={isEditingName}
                nameInput={nameInput}
                onSaveNickname={async (nickname) => {
                  const updated = await updateCurrentUser(apiOptions, { nickname });
                  refreshCurrentUser(updated);
                  setProfileDraft((prev) => ({ ...prev, nickname }));
                }}
                pickerPos={pickerPos}
                preferences={preferences}
                profileAvatarUrl={profileAvatarUrl}
                profileDraft={profileDraft}
                profileLocked={profileLocked}
                setIsEditingName={setIsEditingName}
                setMessage={setMessage}
                setNameInput={setNameInput}
                setPickerPos={setPickerPos}
                setShowAvatarPicker={setShowAvatarPicker}
                showAvatarPicker={showAvatarPicker}
                updatePreference={updatePreference}
              />
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
              <AdminSettingsPanel
                controller={{
                  adminGroupOptions,
                  adminLoading,
                  adminMessage,
                  adminTab,
                  adminUserSearchOptions,
                  adminUsers,
                  auditActionType,
                  auditFilter,
                  auditLogs,
                  auditPage,
                  auditSearch,
                  citationFixerDraft,
                  currentUser,
                  filterAuditLogs,
                  filterReviews,
                  filterTemplates,
                  filterUsers,
                  formatDate,
                  formatFileSize,
                  formatOptionalDate,
                  gbrainContradictionDraft,
                  gbrainDreamDraft,
                  gbrainEntityMerge,
                  gbrainEntityMergePreview,
                  gbrainGraph,
                  gbrainGraphDraft,
                  gbrainMaintenance,
                  handleApplyGBrainEntityMergeCandidate,
                  handleCancelGBrainJob,
                  handleCreateUser,
                  handleExportKnowledgeQualityReport,
                  handleGBrainMaintenanceCheck,
                  handleLoadGBrainEntityMergeCandidates,
                  handleLoadGBrainGraph,
                  handlePollGBrainCitationFixerJobs,
                  handlePollGBrainDreamCycleJobs,
                  handlePreviewGBrainEntityMergeCandidate,
                  handleRefreshGBrainMaintenance,
                  handleRefreshKnowledge,
                  handleRestartGBrain,
                  handleRestartGBrainDreamCycleWorker,
                  handleRetryGBrainJob,
                  handleReviewKnowledge,
                  handleRollbackGBrainCitationFixerJob,
                  handleRunGBrainContradictionProbe,
                  handleRunGBrainDreamCycle,
                  handleRunKnowledgeQualityReport,
                  handleSaveGBrainContradictionProbe,
                  handleSaveGBrainDreamCycle,
                  handleSaveUserGroup,
                  handleStartGBrain,
                  handleSubmitCitationFixer,
                  handleSubmitGBrainJob,
                  handleSubmitReviewCitationFixer,
                  handleTickGBrainContradictionProbe,
                  handleTickGBrainDreamCycle,
                  handleUploadUpdateRelease,
                  isSystemAccount,
                  knowledgeReviews,
                  knowledgeStatus,
                  loadAdminData,
                  newUser,
                  openEditUser,
                  openPasswordDialog,
                  openUserMenuId,
                  paginate,
                  requestDeleteUser,
                  requestRoleChange,
                  requestStatusChange,
                  reviewPage,
                  reviewSearch,
                  setAdminConfirm,
                  setAdminTab,
                  setAuditActionType,
                  setAuditFilter,
                  setAuditPage,
                  setAuditSearch,
                  setCitationFixerDraft,
                  setGBrainContradictionDraft,
                  setGBrainDreamDraft,
                  setGBrainGraphDraft,
                  setNewUser,
                  setOpenUserMenuId,
                  setReviewPage,
                  setReviewSearch,
                  setShowCreateUser,
                  setTemplateSearch,
                  setUpdateDraft,
                  setUpdateFile,
                  setUserGroupDrafts,
                  setUserPage,
                  setUserSearch,
                  setUserSort,
                  shortValue,
                  showCreateUser,
                  sortUsers,
                  statusLabel,
                  templateSearch,
                  templates,
                  uniqueAuditActions,
                  updateDraft,
                  updateFile,
                  updateFileInputRef,
                  updateReleases,
                  userGroupDrafts,
                  userPage,
                  userSearch,
                  userSort,
                  yesNo,
                  asRecord,
                  recordNumber,
                  recordText,
                  canSubmitReviewCitationFixer,
                  toolResultArray,
                  toolStatus,
                }}
              />
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
              <span>{editingUser.username}</span>
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
