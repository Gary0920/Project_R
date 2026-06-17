import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useEffect, useMemo, useRef, useState } from "react";

import { updateCurrentUser, uploadCurrentUserAvatar } from "../../auth/api";
import { ApiError, apiRequest } from "../../../shared/api/client";
import { listArchivedChatSessions, restoreChatSession } from "../../chat/api";
import { listCompanyPrompts } from "../../prompts/api";
import { listSkills } from "../../skills/api";
import type {
  ChatSessionResponse,
  CompanyPromptResponse,
  HealthResponse,
  SkillResponse,
} from "../../../shared/api/types";
import { authTokenAtom, clearAuthAtom, currentUserAtom, refreshCurrentUserAtom } from "../../auth/state";
import { serverUrlAtom, setServerUrlAtom } from "../../../shared/state/server";
import { PROJECT_R_BUILTIN_PROMPT } from "../../prompts/constants";
import { GeneralSection } from "./GeneralSection";
import { AdminSettingsPanel } from "../../admin/components/AdminSettingsPanel";
import { useSettingsAdminController, type AdminTab } from "../hooks/useSettingsAdminController";
import {
  adminConfirmIsDanger,
  adminConfirmText,
  adminConfirmTitle,
  isSystemAccount,
  userDisplayName,
  type AdminUserRole,
} from "../settingsAdminHelpers";
import {
  applyTheme,
  DEFAULT_SHORTCUTS,
  formatDate,
  formatOptionalDate,
  PREFS_KEY,
  readPreferences,
  resolveServerAssetUrl,
  type PreferenceState,
} from "../settingsPreferences";
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
} from "../../../shared/icons/LineIcons";

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
  const [message, setMessage] = useState("保存后会立即测试 /health。");
  const [archivedSessions, setArchivedSessions] = useState<ChatSessionResponse[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [restoringArchiveId, setRestoringArchiveId] = useState<number | null>(null);
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [companyPrompts, setCompanyPrompts] = useState<CompanyPromptResponse[]>([]);
  const [userPrompts, setUserPrompts] = useState<UserPromptRecord[]>([]);
  const [promptDraft, setPromptDraft] = useState({ id: "", name: "", content: "" });
  const apiOptions = useMemo(
    () => ({ baseUrl: serverUrl, token, onUnauthorized: clearAuth }),
    [clearAuth, serverUrl, token],
  );
  const profileAvatarUrl = resolveServerAssetUrl(serverUrl, profileDraft.avatar);
  const profileLocked = currentUser?.username === "sysadmin";
  const {
    adminConfirm,
    controller: adminController,
    editUserDraft,
    editingUser,
    handleConfirmAdminAction,
    handleConfirmPasswordReset,
    handleCopyResetPassword,
    handleSaveEditingUser,
    passwordDialog,
    requestRoleChange,
    setAdminConfirm,
    setAdminTab,
    setEditUserDraft,
    setEditingUser,
    setPasswordDialog,
  } = useSettingsAdminController({
    activeSection,
    apiOptions,
    currentUser,
    isOpen,
    refreshCurrentUser,
  });
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
              <AdminSettingsPanel controller={adminController} />
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
