import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  cancelGBrainJob,
  createAdminUser,
  getGBrainMaintenance,
  listAdminTemplates,
  listAdminUsers,
  listAuditLogs,
  listKnowledgeReviews,
  getKnowledgeStatus,
  refreshKnowledge,
  restartGBrainService,
  retryGBrainJob,
  resetAdminUserPassword,
  reviewKnowledge,
  runGBrainMaintenanceCheck,
  startGBrainService,
  submitGBrainCitationFixer,
  submitGBrainJob,
  updateAdminUser,
} from "../api/admin";
import { updateCurrentUser } from "../api/auth";
import { ApiError, apiRequest } from "../api/client";
import { listArchivedChatSessions, restoreChatSession } from "../api/chat";
import { listCompanyPrompts } from "../api/prompts";
import { listSkills } from "../api/skills";
import { listClientUpdateReleases, uploadClientUpdateRelease } from "../api/updates";
import type {
  AdminTemplateStatusResponse,
  AdminUserResponse,
  AuditLogResponse,
  ChatSessionResponse,
  ClientUpdateInfo,
  CompanyPromptResponse,
  GBrainMaintenanceResponse,
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
  ChatIcon,
  EditIcon,
  NoteIcon,
  PromptIcon,
  SendIcon,
  SettingsIcon,
  ShieldIcon,
  XmarkIcon,
} from "./LineIcons";

type ConnectionState = "idle" | "checking" | "ok" | "error";
type SettingsSection =
  | "general"
  | "server"
  | "prompts"
  | "archive"
  | "agent"
  | "chat"
  | "remote"
  | "tutorial"
  | "shortcuts"
  | "admin";
type AdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type PreferenceState = {
  completionSound: boolean;
  autoArchiveDays: string;
  floatingPinBar: boolean;
  theme: "system" | "light" | "dark";
  memoryEnabled: boolean;
  webSearchEnabled: boolean;
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
      memoryEnabled: true,
      webSearchEnabled: false,
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
      memoryEnabled: true,
      webSearchEnabled: false,
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
  }).format(new Date(value));
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
  chat: "Chat 工具",
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
};

export function SettingsModal({ isOpen, onClose, initialSection, initialAdminTab }: SettingsModalProps) {
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
  const [templates, setTemplates] = useState<AdminTemplateStatusResponse["items"]>([]);
  const [updateReleases, setUpdateReleases] = useState<ClientUpdateInfo[]>([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminMessage, setAdminMessage] = useState("");
  const [newUser, setNewUser] = useState({ username: "", nickname: "", password: "", role: "employee" });
  const [auditFilter, setAuditFilter] = useState({ userId: "", dateFrom: "", dateTo: "" });
  const [citationFixerDraft, setCitationFixerDraft] = useState({
    pageSlug: "",
    reviewId: "",
    slugPrefixes: "",
    notes: "",
    maxTurns: "30",
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

  const apiOptions = useMemo(
    () => ({ baseUrl: serverUrl, token, onUnauthorized: clearAuth }),
    [clearAuth, serverUrl, token],
  );

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
    try {
      const updated = await updateCurrentUser(apiOptions, { nickname: profileDraft.nickname });
      refreshCurrentUser({ ...currentUser!, nickname: updated.nickname });
      setMessage("个人资料已更新。");
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "个人资料保存失败。");
    }
  }

  async function handleRestore(sessionId: number) {
    try {
      await restoreChatSession(apiOptions, sessionId);
      setArchivedSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch {
      // ignore
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

  function handleAvatarImageUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setProfileDraft((prev) => ({ ...prev, avatar: dataUrl }));
      if (currentUser) {
        refreshCurrentUser({ ...currentUser, avatar: dataUrl });
      }
      setShowAvatarPicker(false);
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  }

  function handleSelectEmoji(emoji: string) {
    setProfileDraft((prev) => ({ ...prev, avatar: emoji }));
    if (currentUser) {
      refreshCurrentUser({ ...currentUser, avatar: emoji });
    }
    setShowAvatarPicker(false);
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
      const [users, logs, reviews, templateStatus, updateStatus] = await Promise.all([
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
      ]);
      setAdminUsers(users);
      setAuditLogs(logs);
      setKnowledgeReviews(reviews);
      setTemplates(templateStatus.items);
      setUpdateReleases(updateStatus.items);
      getKnowledgeStatus(apiOptions).then(setKnowledgeStatus).catch(() => setKnowledgeStatus(null));
      getGBrainMaintenance(apiOptions).then(setGBrainMaintenance).catch(() => setGBrainMaintenance(null));
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "管理员数据加载失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleCreateUser() {
    try {
      await createAdminUser(apiOptions, newUser);
      setNewUser({ username: "", nickname: "", password: "", role: "employee" });
      setAdminMessage("用户已创建。");
      await loadAdminData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "创建用户失败。");
    }
  }

  async function handleToggleUser(user: AdminUserResponse) {
    try {
      await updateAdminUser(apiOptions, user.id, { is_active: !user.is_active });
      await loadAdminData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "更新用户状态失败。");
    }
  }

  async function handleToggleRole(user: AdminUserResponse) {
    try {
      await updateAdminUser(apiOptions, user.id, { role: user.role === "admin" ? "employee" : "admin" });
      await loadAdminData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "更新用户角色失败。");
    }
  }

  async function handleResetPassword(user: AdminUserResponse) {
    const password = window.prompt(`为 ${user.username} 设置新密码（至少 8 位）`);
    if (!password) return;
    try {
      await resetAdminUserPassword(apiOptions, user.id, password);
      setAdminMessage("密码已重置。");
      await loadAdminData();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "重置密码失败。");
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
      setGBrainMaintenance(await getGBrainMaintenance(apiOptions));
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "刷新知识库失败。");
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
      setGBrainMaintenance(await getGBrainMaintenance(apiOptions));
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
      setGBrainMaintenance(await getGBrainMaintenance(apiOptions));
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
      let cmp = 0;
      if (sort.field === "username") {
        cmp = a.username.localeCompare(b.username);
      } else if (sort.field === "created_at") {
        cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      }
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }

  function filterReviews(reviews: KnowledgeReviewResponse[], search: string): KnowledgeReviewResponse[] {
    if (!search.trim()) return reviews;
    const s = search.toLowerCase();
    return reviews.filter((r) => (r.source ?? "").toLowerCase().includes(s) || r.content.toLowerCase().includes(s));
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
    { id: "chat", label: "Chat 工具", icon: <ChatIcon /> },
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
                        className="profile-avatar"
                        onClick={() => {
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
                        style={{ cursor: "pointer", position: "relative", width: 64, height: 64, borderRadius: "20%", overflow: "hidden", flexShrink: 0, display: "grid", placeItems: "center", background: "hsl(var(--muted))", fontSize: 28 }}
                      >
                        {profileDraft.avatar?.startsWith("http") || profileDraft.avatar?.startsWith("data:") ? (
                          <img src={profileDraft.avatar} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        ) : (
                          <span>{profileDraft.avatar || "👤"}</span>
                        )}
                        <div
                          style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", background: "rgba(0,0,0,0.4)", opacity: 0, transition: "opacity 0.15s", pointerEvents: "none" }}
                          className="profile-avatar-overlay"
                        >
                          <span style={{ color: "white", fontSize: 12 }}>编辑</span>
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
                              setNameInput(profileDraft.nickname);
                              setIsEditingName(true);
                            }}
                            style={{ fontSize: 18, fontWeight: 600, color: "hsl(var(--foreground))", background: "none", border: "none", padding: 0, cursor: "pointer", textAlign: "left" }}
                          >
                            {profileDraft.nickname || currentUser?.nickname || "未设置昵称"}
                          </button>
                        )}
                        <p style={{ fontSize: 12, color: "hsl(var(--muted-foreground))", marginTop: 4 }}>
                          点击头像更换，点击名字编辑
                        </p>
                      </div>
                    </div>
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
                            onClick={() => void handleRestore(s.id)}
                            type="button"
                          >
                            恢复
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

            {activeSection === "chat" ? (
              <div className="settings-section">
                <div className="settings-section-header">
                  <h3>Chat 工具</h3>
                  <p>聊天辅助功能配置</p>
                </div>
                <div className="settings-card">
                  <div className="settings-option-row">
                    <div>
                      <strong>记忆功能</strong>
                      <span>保留会话上下文与本地偏好</span>
                    </div>
                    <label className="toggle-switch">
                      <input
                        checked={preferences.memoryEnabled}
                        onChange={(event) => updatePreference({ memoryEnabled: event.target.checked })}
                        type="checkbox"
                      />
                      <span className="toggle-switch-slider" />
                    </label>
                  </div>
                  <div className="settings-option-row">
                    <div>
                      <strong>联网搜索</strong>
                      <span>后端能力接入后启用</span>
                    </div>
                    <label className="toggle-switch">
                      <input
                        checked={preferences.webSearchEnabled}
                        onChange={(event) => updatePreference({ webSearchEnabled: event.target.checked })}
                        type="checkbox"
                      />
                      <span className="toggle-switch-slider" />
                    </label>
                  </div>
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
                    <span>例如输入"帮我生成标签打印文件"，系统会进入对话式补参并生成结果文件。</span>
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
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
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
                    </div>
                    <div className="admin-toolbar">
                      <input
                        className="admin-search"
                        placeholder="搜索用户名或昵称"
                        value={userSearch}
                        onChange={(event) => { setUserSearch(event.target.value); setUserPage(1); }}
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
                            <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr) 80px 70px 140px 180px" }}>
                              <span className="sortable" onClick={() => setUserSort((prev) => ({ field: "username", dir: prev.field === "username" && prev.dir === "asc" ? "desc" : "asc" }))}>
                                用户名 {userSort.field === "username" ? (userSort.dir === "asc" ? "↑" : "↓") : ""}
                              </span>
                              <span>昵称</span>
                              <span>角色</span>
                              <span>状态</span>
                              <span className="sortable" onClick={() => setUserSort((prev) => ({ field: "created_at", dir: prev.field === "created_at" && prev.dir === "asc" ? "desc" : "asc" }))}>
                                创建时间 {userSort.field === "created_at" ? (userSort.dir === "asc" ? "↑" : "↓") : ""}
                              </span>
                              <span style={{ textAlign: "right" }}>操作</span>
                            </div>
                            {paged.map((item) => (
                              <div className="admin-table-row" key={item.id} style={{ gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr) 80px 70px 140px 180px" }}>
                                <div className="admin-table-cell">
                                  <div>{item.username}</div>
                                </div>
                                <div className="admin-table-cell">{item.nickname || "-"}</div>
                                <div className="admin-table-cell">{item.role === "admin" ? "管理员" : "员工"}</div>
                                <div className="admin-table-cell">{item.is_active ? "启用" : "禁用"}</div>
                                <div className="admin-table-cell admin-table-cell-secondary">{formatDate(item.created_at)}</div>
                                <div className="admin-table-cell-actions">
                                  <button className="ghost-button" onClick={() => void handleToggleRole(item)} type="button">角色</button>
                                  <button className="ghost-button" onClick={() => void handleToggleUser(item)} type="button">{item.is_active ? "禁用" : "启用"}</button>
                                  <button className="ghost-button" onClick={() => void handleResetPassword(item)} type="button">密码</button>
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
                              <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr) 140px 140px" }}>
                                <span>来源</span>
                                <span>内容</span>
                                <span>提交时间</span>
                                <span style={{ textAlign: "right" }}>操作</span>
                              </div>
                              {paged.map((item) => (
                                <div className="admin-table-row" key={item.id} style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 2fr) 140px 140px" }}>
                                  <div className="admin-table-cell">{item.source || "候选知识"}</div>
                                  <div className="admin-table-cell" title={item.content}>{item.content}</div>
                                  <div className="admin-table-cell admin-table-cell-secondary">{formatDate(item.created_at)}</div>
                                  <div className="admin-table-cell-actions">
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
    </div>
  );
}
