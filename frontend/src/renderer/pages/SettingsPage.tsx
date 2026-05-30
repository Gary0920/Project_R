import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useEffect, useState } from "react";

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
  retryGBrainJob,
  resetAdminUserPassword,
  reviewKnowledge,
  runGBrainMaintenanceCheck,
  runKnowledgeRegression,
  submitGBrainCitationFixer,
  submitGBrainJob,
  updateAdminUser,
} from "../api/admin";
import { updateCurrentUser } from "../api/auth";
import { ApiError, apiRequest } from "../api/client";
import { listArchivedChatSessions, restoreChatSession } from "../api/chat";
import { listCompanyPrompts } from "../api/prompts";
import { listSkills } from "../api/skills";
import type {
  AdminTemplateStatusResponse,
  AdminUserResponse,
  AuditLogResponse,
  ChatSessionResponse,
  CompanyPromptResponse,
  GBrainMaintenanceResponse,
  GBrainToolResponse,
  HealthResponse,
  KnowledgeRegressionResponse,
  KnowledgeReviewResponse,
  KnowledgeStatusResponse,
  SkillResponse,
} from "../api/types";
import { authTokenAtom, clearAuthAtom, currentUserAtom, refreshCurrentUserAtom } from "../atoms/auth-atoms";
import { serverUrlAtom, setServerUrlAtom } from "../atoms/server-atoms";
import { PROJECT_R_BUILTIN_PROMPT } from "../constants/prompts";

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

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function recordList(response?: GBrainToolResponse | null, nestedKey?: string): Array<Record<string, unknown>> {
  const result = response?.result;
  if (Array.isArray(result)) return result.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
  if (!result || typeof result !== "object" || Array.isArray(result)) return [];
  const nested = (result as Record<string, unknown>)[nestedKey ?? ""];
  if (!Array.isArray(nested)) return [];
  return nested.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
}

function recordText(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function statusLabel(value?: string | null) {
  if (!value) return "-";
  const labels: Record<string, string> = {
    disabled: "已禁用",
    oauth_required: "缺 OAuth",
    configured_unverified: "已配置未验收",
    ready: "可执行",
  };
  return labels[value] ?? value;
}

function recordNumber(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function optionalRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

export function SettingsPage() {
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
  const [message, setMessage] = useState("保存后会立即测试 /health。");
  const [archivedSessions, setArchivedSessions] = useState<ChatSessionResponse[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [companyPrompts, setCompanyPrompts] = useState<CompanyPromptResponse[]>([]);
  const [userPrompts, setUserPrompts] = useState<UserPromptRecord[]>([]);
  const [promptDraft, setPromptDraft] = useState({ id: "", name: "", content: "" });
  const [adminUsers, setAdminUsers] = useState<AdminUserResponse[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [knowledgeReviews, setKnowledgeReviews] = useState<KnowledgeReviewResponse[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatusResponse | null>(null);
  const [knowledgeRegression, setKnowledgeRegression] = useState<KnowledgeRegressionResponse | null>(null);
  const [gbrainMaintenance, setGBrainMaintenance] = useState<GBrainMaintenanceResponse | null>(null);
  const [templates, setTemplates] = useState<AdminTemplateStatusResponse["items"]>([]);
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

  const apiOptions = { baseUrl: serverUrl, token, onUnauthorized: clearAuth };

  useEffect(() => {
    setArchiveLoading(true);
    listArchivedChatSessions(apiOptions)
      .then(setArchivedSessions)
      .catch(() => {})
      .finally(() => setArchiveLoading(false));
  }, [serverUrl, token]);

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
    if (currentUser?.role !== "admin") return;
    void loadAdminData();
  }, [currentUser?.role, serverUrl, token]);

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
      const updated = await updateCurrentUser(apiOptions, profileDraft);
      refreshCurrentUser(updated);
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

  async function handleDeleteUserPrompt(id: string) {
    const next = await window.projectR?.prompts?.deleteUser(id);
    setUserPrompts(next ?? []);
    if (promptDraft.id === id) setPromptDraft({ id: "", name: "", content: "" });
  }

  async function loadAdminData() {
    setAdminLoading(true);
    setAdminMessage("");
    try {
      const [users, logs, reviews, templateStatus] = await Promise.all([
        listAdminUsers(apiOptions),
        listAuditLogs(apiOptions, {
          user_id: auditFilter.userId ? Number(auditFilter.userId) : undefined,
          date_from: auditFilter.dateFrom ? new Date(auditFilter.dateFrom).toISOString() : undefined,
          date_to: auditFilter.dateTo ? new Date(`${auditFilter.dateTo}T23:59:59`).toISOString() : undefined,
          limit: 20,
        }),
        listKnowledgeReviews(apiOptions, "pending"),
        listAdminTemplates(apiOptions),
      ]);
      setAdminUsers(users);
      setAuditLogs(logs);
      setKnowledgeReviews(reviews);
      setTemplates(templateStatus.items);
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

  async function handleRefreshKnowledge() {
    setAdminLoading(true);
    setAdminMessage("正在刷新知识库...");
    try {
      const result = await refreshKnowledge(apiOptions);
      setAdminMessage(result.ok ? `刷新完成：${result.indexed} 个文件，${result.chunks} 个片段。` : result.error ?? "刷新失败。");
      setKnowledgeStatus(await getKnowledgeStatus(apiOptions));
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "刷新知识库失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function handleKnowledgeRegression(includeThink = false) {
    setAdminLoading(true);
    setAdminMessage(includeThink ? "正在运行 GBrain 查询 + Think 回归..." : "正在运行 GBrain 查询回归...");
    try {
      const result = await runKnowledgeRegression(apiOptions, includeThink);
      setKnowledgeRegression(result);
      const queryText = `${result.query.passed}/${result.query.total}`;
      const thinkText = result.think.skipped ? "未运行" : `${result.think.passed}/${result.think.total}`;
      setAdminMessage(result.ok ? `回归通过：query ${queryText}，think ${thinkText}。` : `回归未通过：query ${queryText}，think ${thinkText}。`);
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "运行知识库回归失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  async function refreshGBrainMaintenance(message = "") {
    const result = await getGBrainMaintenance(apiOptions);
    setGBrainMaintenance(result);
    if (message) setAdminMessage(message);
    return result;
  }

  async function handleGBrainMaintenanceCheck() {
    setAdminLoading(true);
    setAdminMessage("正在运行 GBrain 维护检查...");
    try {
      const result = await runGBrainMaintenanceCheck(apiOptions, 90);
      setAdminMessage(result.ok ? "GBrain 维护检查完成。" : "GBrain 维护检查失败。");
      await refreshGBrainMaintenance();
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
      await refreshGBrainMaintenance();
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
      await refreshGBrainMaintenance();
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
      await refreshGBrainMaintenance();
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
      const job = optionalRecord(result.result);
      const jobId = job ? recordNumber(job, "id") : null;
      setAdminMessage(
        result.status === "ok"
          ? `GBrain citation-fixer 已提交${jobId ? `：#${jobId}` : ""}。`
          : result.error || "GBrain citation-fixer 提交失败。",
      );
      await refreshGBrainMaintenance();
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "GBrain citation-fixer 提交失败。");
    } finally {
      setAdminLoading(false);
    }
  }

  const visibleSections: Array<{ id: SettingsSection; label: string }> = [
    { id: "general", label: "通用" },
    { id: "server", label: "服务器" },
    { id: "prompts", label: "提示词" },
    { id: "archive", label: "归档" },
    { id: "agent", label: "Agent" },
    { id: "chat", label: "Chat 工具" },
    { id: "remote", label: "远程连接" },
    { id: "tutorial", label: "教程" },
    { id: "shortcuts", label: "快捷键" },
    ...(currentUser?.role === "admin" ? [{ id: "admin" as const, label: "管理员" }] : []),
  ];

  return (
    <main className="page settings-page-shell">
      <aside className="settings-nav">
        <a className="settings-back" href="#/app">返回工作台</a>
        {visibleSections.map((section) => (
          <button
            className={activeSection === section.id ? "is-active" : ""}
            key={section.id}
            onClick={() => setActiveSection(section.id)}
            type="button"
          >
            {section.label}
          </button>
        ))}
      </aside>

      <div className="settings-content">
      {activeSection === "general" ? (
      <section className="panel settings-panel">
        <p className="eyebrow">General</p>
        <h1>通用设置</h1>
        <label className="field">
          <span>昵称</span>
          <input
            value={profileDraft.nickname}
            onChange={(event) => setProfileDraft((prev) => ({ ...prev, nickname: event.target.value }))}
          />
        </label>
        <label className="field">
          <span>头像标识</span>
          <input
            maxLength={32}
            placeholder="例如 R / Gary / 头像 URL"
            value={profileDraft.avatar}
            onChange={(event) => setProfileDraft((prev) => ({ ...prev, avatar: event.target.value }))}
          />
        </label>
        <div className="button-row">
          <button onClick={() => void handleSaveProfile()} type="button">保存个人资料</button>
        </div>
        <div className="settings-option-row">
          <div>
            <strong>界面语言</strong>
            <span>当前仅支持简体中文</span>
          </div>
          <select disabled value="zh-CN">
            <option value="zh-CN">简体中文</option>
            <option value="en-US">English 即将支持</option>
          </select>
        </div>
        <div className="settings-option-row">
          <div>
            <strong>任务完成音效</strong>
            <span>Agent 工作流完成后播放提示音</span>
          </div>
          <input
            checked={preferences.completionSound}
            onChange={(event) => updatePreference({ completionSound: event.target.checked })}
            type="checkbox"
          />
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
          <input
            checked={preferences.floatingPinBar}
            onChange={(event) => updatePreference({ floatingPinBar: event.target.checked })}
            type="checkbox"
          />
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
      </section>
      ) : null}

      {activeSection === "server" ? (
      <section className="panel settings-panel">
        <p className="eyebrow">Settings</p>
        <h1>服务器连接</h1>
        <p className="lede">后端地址由本地配置管理，保存后会立即检查连接状态。</p>
        <label className="field">
          <span>后端地址</span>
          <input value={draft} onChange={(event) => setDraft(event.target.value)} />
        </label>
        <div className="button-row">
          <button onClick={handleSave}>保存并测试</button>
          <button className="ghost-button" onClick={() => void testConnection()} type="button">
            仅测试连接
          </button>
        </div>
        <p className={`connection-status connection-status-${connectionState}`}>{message}</p>
        <p className="meta">当前生效：{serverUrl}</p>
      </section>
      ) : null}

      {activeSection === "archive" ? (
      <section className="panel settings-panel">
        <p className="eyebrow">归档管理</p>
        <h1>已归档对话</h1>
        <p className="lede">归档的对话不会出现在侧栏中，但可以在此恢复。</p>

        {archiveLoading ? (
          <p className="meta">正在加载...</p>
        ) : archivedSessions.length === 0 ? (
          <p className="meta">暂无已归档对话。</p>
        ) : (
          <div className="archive-list">
            {archivedSessions.map((s) => (
              <div className="archive-item" key={s.id}>
                <div className="archive-item-info">
                  <span className="archive-item-title">{s.title}</span>
                  <span className="archive-item-time">{formatDate(s.updated_at)}</span>
                </div>
                <button
                  className="archive-restore-btn"
                  onClick={() => void handleRestore(s.id)}
                  type="button"
                >
                  恢复
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
      ) : null}

      {activeSection === "prompts" ? (
      <section className="panel settings-panel settings-wide-panel">
        <p className="eyebrow">Prompts</p>
        <h1>提示词管理</h1>
        <div className="settings-prompt-grid">
          <section>
            <h2>内置提示词</h2>
            <div className="admin-row">
              <div>
                <strong>{PROJECT_R_BUILTIN_PROMPT.name}</strong>
                <span>Project_R 默认，只读</span>
              </div>
            </div>
          </section>
          <section>
            <h2>公司预设</h2>
            <div className="admin-list">
              {companyPrompts.map((prompt) => (
                <div className="admin-row" key={prompt.id}>
                  <div>
                    <strong>{prompt.name}</strong>
                    <span>{prompt.description || "后端预设，只读"}</span>
                  </div>
                </div>
              ))}
              {companyPrompts.length === 0 ? <p className="meta">暂无公司预设。</p> : null}
            </div>
          </section>
          <section>
            <h2>本机自定义</h2>
            <div className="settings-prompt-editor">
              <input
                placeholder="提示词名称"
                value={promptDraft.name}
                onChange={(event) => setPromptDraft((prev) => ({ ...prev, name: event.target.value }))}
              />
              <textarea
                placeholder="输入系统提示词内容..."
                value={promptDraft.content}
                onChange={(event) => setPromptDraft((prev) => ({ ...prev, content: event.target.value }))}
              />
              <div className="button-row">
                <button disabled={!promptDraft.name.trim() || !promptDraft.content.trim()} onClick={() => void handleSaveUserPrompt()} type="button">
                  {promptDraft.id ? "保存修改" : "新建提示词"}
                </button>
                {promptDraft.id ? (
                  <button className="ghost-button" onClick={() => setPromptDraft({ id: "", name: "", content: "" })} type="button">取消编辑</button>
                ) : null}
              </div>
            </div>
            <div className="admin-list">
              {userPrompts.map((prompt) => (
                <div className="admin-row" key={prompt.id}>
                  <div>
                    <strong>{prompt.name}</strong>
                    <span>{prompt.content}</span>
                  </div>
                  <div className="admin-row-actions">
                    <button className="ghost-button" onClick={() => setPromptDraft({ id: prompt.id, name: prompt.name, content: prompt.content })} type="button">编辑</button>
                    <button className="ghost-button" onClick={() => void handleDeleteUserPrompt(prompt.id)} type="button">删除</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>
      ) : null}

      {activeSection === "agent" ? (
      <section className="panel settings-panel">
        <p className="eyebrow">Agent</p>
        <h1>Agent 配置</h1>
        <p className="lede">官方 Skills 与企业 Skills 只读展示，执行配置由后端统一管理。</p>
        <div className="admin-list">
          {skills.map((skill) => (
            <div className="admin-row" key={skill.name}>
              <div>
                <strong>{skill.display_name}</strong>
                <span>{skill.name} · {skill.category || "未分类"} · {skill.priority}</span>
              </div>
            </div>
          ))}
          {skills.length === 0 ? <p className="meta">暂无可用 Skill。</p> : null}
        </div>
      </section>
      ) : null}

      {activeSection === "chat" ? (
      <section className="panel settings-panel">
        <p className="eyebrow">Chat</p>
        <h1>Chat 工具</h1>
        <div className="settings-option-row">
          <div>
            <strong>记忆功能</strong>
            <span>保留会话上下文与本地偏好</span>
          </div>
          <input
            checked={preferences.memoryEnabled}
            onChange={(event) => updatePreference({ memoryEnabled: event.target.checked })}
            type="checkbox"
          />
        </div>
        <div className="settings-option-row">
          <div>
            <strong>联网搜索</strong>
            <span>后端能力接入后启用</span>
          </div>
          <input
            checked={preferences.webSearchEnabled}
            onChange={(event) => updatePreference({ webSearchEnabled: event.target.checked })}
            type="checkbox"
          />
        </div>
      </section>
      ) : null}

      {activeSection === "remote" ? (
      <section className="panel settings-panel">
        <p className="eyebrow">Remote</p>
        <h1>远程连接</h1>
        <label className="field">
          <span>钉钉 Webhook</span>
          <input
            value={preferences.dingTalkWebhook}
            onChange={(event) => updatePreference({ dingTalkWebhook: event.target.value })}
          />
        </label>
        <label className="field">
          <span>钉钉 Token</span>
          <input
            value={preferences.dingTalkToken}
            onChange={(event) => updatePreference({ dingTalkToken: event.target.value })}
          />
        </label>
      </section>
      ) : null}

      {activeSection === "tutorial" ? (
      <section className="panel settings-panel settings-wide-panel">
        <p className="eyebrow">Guide</p>
        <h1>软件教程</h1>
        <div className="settings-tutorial">
          <h2>开始工作</h2>
              <p>创建或选择项目，在 Chat 中提问，在 Agent 中查看项目文件。</p>
          <h2>知识库问答</h2>
          <p>使用普通提问或 `/query` 固定知识库模式，回答会显示来源。</p>
          <h2>业务 Skill</h2>
          <p>例如输入“帮我生成标签打印文件”，系统会进入对话式补参并生成结果文件。</p>
        </div>
      </section>
      ) : null}

      {activeSection === "shortcuts" ? (
      <section className="panel settings-panel">
        <p className="eyebrow">Shortcuts</p>
        <h1>快捷键管理</h1>
        <div className="admin-list">
          {[
            ["newChat", "新建对话"],
            ["search", "搜索对话"],
            ["settings", "打开设置"],
            ["send", "发送消息"],
            ["newline", "换行"],
          ].map(([key, label]) => (
            <div className="admin-row settings-shortcut-row" key={key}>
              <div>
                <strong>{label}</strong>
              </div>
              <input
                value={preferences.shortcuts?.[key] ?? DEFAULT_SHORTCUTS[key]}
                onChange={(event) => updatePreference({
                  shortcuts: { ...(preferences.shortcuts ?? DEFAULT_SHORTCUTS), [key]: event.target.value },
                })}
              />
            </div>
          ))}
        </div>
      </section>
      ) : null}

      {activeSection === "admin" && currentUser?.role === "admin" ? (
        <section className="panel settings-panel settings-admin-panel">
          <div className="settings-section-title">
            <div>
              <p className="eyebrow">Admin</p>
              <h1>管理员后台</h1>
            </div>
            <button className="ghost-button" onClick={() => void loadAdminData()} type="button">
              刷新
            </button>
          </div>
          {adminMessage ? <p className="connection-status connection-status-idle">{adminMessage}</p> : null}
          {adminLoading ? <p className="meta">正在加载管理员数据...</p> : null}

          <div className="admin-section">
            <div className="settings-section-title">
              <h2>知识库管理</h2>
              <div className="settings-section-actions">
                <button className="ghost-button" onClick={() => void handleRefreshKnowledge()} type="button">
                  刷新索引
                </button>
                <button className="ghost-button" onClick={() => void handleKnowledgeRegression()} type="button">
                  查询回归
                </button>
                <button className="ghost-button" onClick={() => void handleKnowledgeRegression(true)} type="button">
                  Think 回归
                </button>
              </div>
            </div>
            <div className="admin-metric-grid">
              <div>
                <strong>{knowledgeStatus?.indexed_files ?? "-"}</strong>
                <span>索引文件</span>
              </div>
              <div>
                <strong>{knowledgeStatus?.indexed_chunks ?? "-"}</strong>
                <span>片段数量</span>
              </div>
              <div>
                <strong>{knowledgeStatus?.embedding_model ?? "-"}</strong>
                <span>嵌入模型</span>
              </div>
            </div>
            {knowledgeRegression ? (
              <div className="admin-regression-report">
                <div className="admin-regression-summary">
                  <span className={knowledgeRegression.ok ? "status-pill status-pill-success" : "status-pill status-pill-warning"}>
                    {knowledgeRegression.ok ? "通过" : "未通过"}
                  </span>
                  <span>Query {knowledgeRegression.query.passed}/{knowledgeRegression.query.total}</span>
                  <span>
                    Think {knowledgeRegression.think.skipped ? "未运行" : `${knowledgeRegression.think.passed}/${knowledgeRegression.think.total}`}
                  </span>
                </div>
                {[knowledgeRegression.query, knowledgeRegression.think].flatMap((suite) =>
                  suite.cases.filter((item) => !item.ok).map((item) => (
                    <p className="meta" key={`${suite === knowledgeRegression.query ? "query" : "think"}-${item.id}`}>
                      {item.id}: {item.reason || "失败"}
                    </p>
                  )),
                )}
                {[...(knowledgeRegression.query.preflight_failures ?? []), ...(knowledgeRegression.think.preflight_failures ?? [])].map((failure) => (
                  <p className="meta" key={failure}>{failure}</p>
                ))}
              </div>
            ) : null}
          </div>

          <div className="admin-section">
            <div className="settings-section-title">
              <h2>GBrain 维护</h2>
              <div className="settings-section-actions">
                <button className="ghost-button" onClick={() => void refreshGBrainMaintenance("GBrain 维护状态已刷新。")} type="button">
                  刷新维护
                </button>
                <button className="ghost-button" onClick={() => void handleGBrainMaintenanceCheck()} type="button">
                  维护检查
                </button>
                <button className="ghost-button" onClick={() => void handleSubmitGBrainJob("sync")} type="button">
                  sync
                </button>
                <button className="ghost-button" onClick={() => void handleSubmitGBrainJob("embed")} type="button">
                  embed
                </button>
              </div>
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
            {(() => {
              const jobs = recordList(gbrainMaintenance?.jobs);
              const contradictions = recordList(gbrainMaintenance?.contradictions, "contradictions");
              const doctorSummary = gbrainMaintenance?.doctor_summary ?? {};
              const agentStatus = optionalRecord(gbrainMaintenance?.agent);
              const healthScore = typeof doctorSummary.health_score === "number" ? doctorSummary.health_score : "-";
              return (
                <>
                  <div className="admin-metric-grid">
                    <div>
                      <strong>{gbrainMaintenance?.ok ? "正常" : "需检查"}</strong>
                      <span>维护状态</span>
                    </div>
                    <div>
                      <strong>{healthScore}</strong>
                      <span>doctor 分数</span>
                    </div>
                    <div>
                      <strong>{jobs.length}</strong>
                      <span>最近任务</span>
                    </div>
                    <div>
                      <strong>{contradictions.length}</strong>
                      <span>冲突记录</span>
                    </div>
                    <div>
                      <strong>{agentStatus ? statusLabel(recordText(agentStatus, "status")) : "-"}</strong>
                      <span>agent OAuth</span>
                    </div>
                  </div>
                  <div className="admin-list">
                    {jobs.map((job, index) => {
                      const jobId = recordNumber(job, "id");
                      return (
                        <div className="admin-row" key={`${jobId ?? "job"}-${index}`}>
                          <div>
                            <strong>#{jobId ?? "-"} · {recordText(job, "name") || "job"}</strong>
                            <span>{recordText(job, "status") || "-"} · {JSON.stringify(job.progress ?? job.error ?? {}).slice(0, 120)}</span>
                          </div>
                          <div style={{ display: "flex", gap: 8 }}>
                            <button className="ghost-button" disabled={!jobId} onClick={() => jobId && void handleCancelGBrainJob(jobId)} type="button">取消</button>
                            <button className="ghost-button" disabled={!jobId} onClick={() => jobId && void handleRetryGBrainJob(jobId)} type="button">重试</button>
                          </div>
                        </div>
                      );
                    })}
                    {jobs.length === 0 ? (
                      <div className="admin-row">
                        <div>
                          <strong>暂无 GBrain 维护任务</strong>
                          <span>可先运行维护检查或提交 sync/embed 任务。</span>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </>
              );
            })()}
          </div>

          <div className="admin-section">
            <h2>用户管理</h2>
            <div className="admin-create-user">
              <input
                placeholder="用户名"
                value={newUser.username}
                onChange={(event) => setNewUser((prev) => ({ ...prev, username: event.target.value }))}
              />
              <input
                placeholder="昵称"
                value={newUser.nickname}
                onChange={(event) => setNewUser((prev) => ({ ...prev, nickname: event.target.value }))}
              />
              <input
                placeholder="初始密码"
                type="password"
                value={newUser.password}
                onChange={(event) => setNewUser((prev) => ({ ...prev, password: event.target.value }))}
              />
              <select
                value={newUser.role}
                onChange={(event) => setNewUser((prev) => ({ ...prev, role: event.target.value }))}
              >
                <option value="employee">员工</option>
                <option value="admin">管理员</option>
              </select>
              <button onClick={() => void handleCreateUser()} type="button">新增</button>
            </div>
            <div className="admin-list">
              {adminUsers.map((item) => (
                <div className="admin-row" key={item.id}>
                  <div>
                    <strong>{item.nickname || item.username}</strong>
                    <span>{item.username} · {item.role === "admin" ? "管理员" : "员工"} · {item.is_active ? "启用" : "禁用"}</span>
                  </div>
                  <div className="admin-row-actions">
                    <button className="ghost-button" onClick={() => void handleToggleRole(item)} type="button">角色</button>
                    <button className="ghost-button" onClick={() => void handleToggleUser(item)} type="button">
                      {item.is_active ? "禁用" : "启用"}
                    </button>
                    <button className="ghost-button" onClick={() => void handleResetPassword(item)} type="button">密码</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="admin-section">
            <h2>知识审核</h2>
            {knowledgeReviews.length === 0 ? (
              <p className="meta">暂无待审核知识。</p>
            ) : (
              <div className="admin-list">
                {knowledgeReviews.map((item) => (
                  <div className="admin-row admin-row-tall" key={item.id}>
                    <div>
                      <strong>{item.source || "候选知识"}</strong>
                      <span>{item.content}</span>
                    </div>
                    <div className="admin-row-actions">
                      <button className="ghost-button" onClick={() => void handleReviewKnowledge(item, "approved")} type="button">通过</button>
                      <button className="ghost-button" onClick={() => void handleReviewKnowledge(item, "rejected")} type="button">驳回</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="admin-section admin-two-col">
            <div>
              <h2>模板 / Skill</h2>
              <div className="admin-list">
                {templates.map((item) => (
                  <div className="admin-row" key={item.skill_name}>
                    <div>
                      <strong>{item.display_name}</strong>
                      <span>{item.skill_name} · {item.outputs.map((output) => String(output.format ?? output.type ?? "output")).join(", ")}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h2>近期审计</h2>
              <div className="admin-audit-filters">
                <input
                  placeholder="用户 ID"
                  value={auditFilter.userId}
                  onChange={(event) => setAuditFilter((prev) => ({ ...prev, userId: event.target.value }))}
                />
                <input
                  type="date"
                  value={auditFilter.dateFrom}
                  onChange={(event) => setAuditFilter((prev) => ({ ...prev, dateFrom: event.target.value }))}
                />
                <input
                  type="date"
                  value={auditFilter.dateTo}
                  onChange={(event) => setAuditFilter((prev) => ({ ...prev, dateTo: event.target.value }))}
                />
                <button className="ghost-button" onClick={() => void loadAdminData()} type="button">筛选</button>
              </div>
              <div className="admin-list">
                {auditLogs.map((item) => (
                  <div className="admin-row" key={item.id}>
                    <div>
                      <strong>{item.action}</strong>
                      <span>{formatDate(item.created_at)} · user #{item.user_id} · {item.success ? "成功" : "失败"}</span>
                    </div>
                    {item.token_cost ? <span className="admin-token">{item.token_cost}</span> : null}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      ) : null}
      </div>
    </main>
  );
}
