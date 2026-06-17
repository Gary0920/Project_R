import type { RefObject } from "react";

import type {
  AdminTemplateStatusResponse,
  AdminUserResponse,
  AuditLogResponse,
  ClientUpdateInfo,
  CurrentUserResponse,
  GBrainEntityMergeCandidate,
  GBrainEntityMergeCandidatesResponse,
  GBrainEntityMergePreviewResponse,
  GBrainGraphResponse,
  GBrainMaintenanceResponse,
  GBrainToolResponse,
  KnowledgeReviewResponse,
  KnowledgeStatusResponse,
} from "../../../shared/api/types";
import { ChevronDownIcon, EditIcon, MoreIcon, SearchIcon, ShieldIcon } from "../../../shared/icons/LineIcons";
import { AdminKnowledgeOverview } from "../knowledge/AdminKnowledgeOverview";
import { AdminGBrainSection } from "./AdminGBrainSection";
import { KnowledgeReviewPanel } from "../knowledge/reviews/KnowledgeReviewPanel";
import { AdminComboInput, type AdminComboOption } from "../../settings/components/AdminComboInput";

type AdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type AdminUserRole = "admin" | "employee";
type DraftSetter<T> = { bivarianceHack(value: T | ((prev: T) => T)): void }["bivarianceHack"];
type AuditFilterDraft = { userId: string; dateFrom: string; dateTo: string };
type CitationFixerDraft = { pageSlug: string; reviewId: string; slugPrefixes: string; notes: string; maxTurns: string };
type GBrainGraphDraft = { sourceId: string; focus: string; entityType: string };
type GBrainDreamDraft = { enabled: boolean; intervalHours: string; targetScore: string; sourceId: string; jobNames: string };
type GBrainContradictionDraft = {
  enabled: boolean;
  intervalHours: string;
  sourceId: string;
  queries: string;
  topK: string;
  budgetUsd: string;
  judgeModel: string;
  timeoutSeconds: string;
  resultLimit: string;
};
type NewUserDraft = { username: string; nickname: string; password: string; role: string; work_group: string };
type UpdateReleaseDraft = {
  version: string;
  minimumSupportedVersion: string;
  platform: string;
  releaseNotes: string;
  isForceUpdate: boolean;
  isActive: boolean;
};

export type AdminSettingsPanelController = {
  adminGroupOptions: AdminComboOption[];
  adminLoading: boolean;
  adminMessage: string;
  adminTab: AdminTab;
  adminUserSearchOptions: AdminComboOption[];
  adminUsers: AdminUserResponse[];
  auditActionType: string;
  auditFilter: AuditFilterDraft;
  auditLogs: AuditLogResponse[];
  auditPage: number;
  auditSearch: string;
  citationFixerDraft: CitationFixerDraft;
  currentUser: CurrentUserResponse | null;
  filterAuditLogs: (logs: AuditLogResponse[], search: string, actionType: string) => AuditLogResponse[];
  filterTemplates: (templates: AdminTemplateStatusResponse["items"], search: string) => AdminTemplateStatusResponse["items"];
  filterUsers: (users: AdminUserResponse[], search: string) => AdminUserResponse[];
  formatDate: (value: string | number) => string;
  formatFileSize: (bytes: number) => string;
  formatOptionalDate: (value?: string | null) => string;
  gbrainContradictionDraft: GBrainContradictionDraft;
  gbrainDreamDraft: GBrainDreamDraft;
  gbrainEntityMerge: GBrainEntityMergeCandidatesResponse | null;
  gbrainEntityMergePreview: GBrainEntityMergePreviewResponse | null;
  gbrainGraph: GBrainGraphResponse | null;
  gbrainGraphDraft: GBrainGraphDraft;
  gbrainMaintenance: GBrainMaintenanceResponse | null;
  handleApplyGBrainEntityMergeCandidate: (candidate: GBrainEntityMergeCandidate, action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes") => Promise<void>;
  handleCancelGBrainJob: (jobId: number) => Promise<void>;
  handleCreateUser: () => Promise<void>;
  handleExportKnowledgeQualityReport: (reportId?: string | null) => Promise<void>;
  handleGBrainMaintenanceCheck: () => Promise<void>;
  handleLoadGBrainEntityMergeCandidates: () => Promise<void>;
  handleLoadGBrainGraph: () => Promise<void>;
  handlePollGBrainCitationFixerJobs: () => Promise<void>;
  handlePollGBrainDreamCycleJobs: () => Promise<void>;
  handlePreviewGBrainEntityMergeCandidate: (candidate: GBrainEntityMergeCandidate) => Promise<void>;
  handleRefreshGBrainMaintenance: () => Promise<void>;
  handleRefreshKnowledge: (enablePdfStructuredExtraction?: boolean) => Promise<void>;
  handleRestartGBrain: () => Promise<void>;
  handleRestartGBrainDreamCycleWorker: () => Promise<void>;
  handleRetryGBrainJob: (jobId: number) => Promise<void>;
  handleReviewKnowledge: (item: KnowledgeReviewResponse, status: "approved" | "rejected", content?: string) => Promise<boolean>;
  handleRollbackGBrainCitationFixerJob: (jobId: number) => Promise<void>;
  handleRunGBrainContradictionProbe: () => Promise<void>;
  handleRunGBrainDreamCycle: () => Promise<void>;
  handleRunKnowledgeQualityReport: (includeThink?: boolean) => Promise<void>;
  handleSaveGBrainContradictionProbe: () => Promise<void>;
  handleSaveGBrainDreamCycle: () => Promise<void>;
  handleSaveUserGroup: (user: AdminUserResponse, value: string) => Promise<void>;
  handleStartGBrain: () => Promise<void>;
  handleSubmitCitationFixer: () => Promise<void>;
  handleSubmitGBrainJob: (name: "sync" | "embed" | "lint" | "backlinks") => Promise<void>;
  handleSubmitReviewCitationFixer: (item: KnowledgeReviewResponse) => Promise<void>;
  handleTickGBrainContradictionProbe: () => Promise<void>;
  handleTickGBrainDreamCycle: () => Promise<void>;
  handleUploadUpdateRelease: () => Promise<void>;
  isSystemAccount: (user: AdminUserResponse | null | undefined) => boolean;
  knowledgeReviews: KnowledgeReviewResponse[];
  knowledgeStatus: KnowledgeStatusResponse | null;
  loadAdminData: () => Promise<void>;
  newUser: NewUserDraft;
  openEditUser: (user: AdminUserResponse) => void;
  openPasswordDialog: (user: AdminUserResponse) => void;
  openUserMenuId: number | null;
  paginate: <T>(items: T[], page: number, pageSize: number) => T[];
  requestDeleteUser: (user: AdminUserResponse) => void;
  requestRoleChange: (user: AdminUserResponse, nextRole: AdminUserRole) => void;
  requestStatusChange: (user: AdminUserResponse, nextActive: boolean) => void;
  reviewPage: number;
  reviewSearch: string;
  setAdminConfirm: DraftSetter<any>;
  setAdminTab: DraftSetter<AdminTab>;
  setAuditActionType: DraftSetter<string>;
  setAuditFilter: DraftSetter<AuditFilterDraft>;
  setAuditPage: DraftSetter<number>;
  setAuditSearch: DraftSetter<string>;
  setCitationFixerDraft: DraftSetter<CitationFixerDraft>;
  setGBrainContradictionDraft: DraftSetter<GBrainContradictionDraft>;
  setGBrainDreamDraft: DraftSetter<GBrainDreamDraft>;
  setGBrainGraphDraft: DraftSetter<GBrainGraphDraft>;
  setNewUser: DraftSetter<NewUserDraft>;
  setOpenUserMenuId: DraftSetter<number | null>;
  setReviewPage: DraftSetter<number>;
  setReviewSearch: DraftSetter<string>;
  setShowCreateUser: DraftSetter<boolean>;
  setTemplateSearch: DraftSetter<string>;
  setUpdateDraft: DraftSetter<UpdateReleaseDraft>;
  setUpdateFile: DraftSetter<File | null>;
  setUserGroupDrafts: DraftSetter<Record<number, string>>;
  setUserPage: DraftSetter<number>;
  setUserSearch: DraftSetter<string>;
  setUserSort: DraftSetter<{ field: "username" | "created_at"; dir: "asc" | "desc" }>;
  shortValue: (value: unknown) => string;
  showCreateUser: boolean;
  sortUsers: (users: AdminUserResponse[], sort: { field: "username" | "created_at"; dir: "asc" | "desc" }) => AdminUserResponse[];
  statusLabel: (value?: string | null) => string;
  templateSearch: string;
  templates: AdminTemplateStatusResponse["items"];
  uniqueAuditActions: string[];
  updateDraft: UpdateReleaseDraft;
  updateFile: File | null;
  updateFileInputRef: RefObject<HTMLInputElement | null>;
  updateReleases: ClientUpdateInfo[];
  userGroupDrafts: Record<number, string>;
  userPage: number;
  userSearch: string;
  userSort: { field: "username" | "created_at"; dir: "asc" | "desc" };
  yesNo: (value?: boolean | null) => string;
  asRecord: (value: unknown) => Record<string, unknown> | null;
  recordNumber: (record: Record<string, unknown> | null | undefined, key: string) => number | null;
  recordText: (record: Record<string, unknown> | null | undefined, key: string) => string;
  toolResultArray: (response?: GBrainToolResponse | null, nestedKey?: string) => Array<Record<string, unknown>>;
  toolStatus: (response?: GBrainToolResponse | null) => string;
};

export type AdminSettingsPanelProps = {
  controller: AdminSettingsPanelController;
};

export function AdminSettingsPanel({ controller }: AdminSettingsPanelProps) {
  const {
    adminGroupOptions, adminLoading, adminMessage, adminTab, adminUserSearchOptions, adminUsers, auditActionType, auditFilter, auditLogs, auditPage, auditSearch,
    citationFixerDraft, currentUser, filterAuditLogs, filterTemplates, filterUsers,
    formatDate, formatFileSize, formatOptionalDate, gbrainContradictionDraft, gbrainDreamDraft, gbrainEntityMerge, gbrainEntityMergePreview, gbrainGraph, gbrainGraphDraft,
    gbrainMaintenance, handleApplyGBrainEntityMergeCandidate, handleCancelGBrainJob, handleCreateUser, handleExportKnowledgeQualityReport, handleGBrainMaintenanceCheck, handleLoadGBrainEntityMergeCandidates,
    handleLoadGBrainGraph, handlePollGBrainCitationFixerJobs, handlePollGBrainDreamCycleJobs, handlePreviewGBrainEntityMergeCandidate, handleRefreshGBrainMaintenance,
    handleRefreshKnowledge, handleRestartGBrain, handleRestartGBrainDreamCycleWorker, handleRetryGBrainJob, handleReviewKnowledge, handleRollbackGBrainCitationFixerJob,
    handleRunGBrainContradictionProbe, handleRunGBrainDreamCycle, handleRunKnowledgeQualityReport, handleSaveGBrainContradictionProbe, handleSaveGBrainDreamCycle,
    handleSaveUserGroup, handleStartGBrain, handleSubmitCitationFixer, handleSubmitGBrainJob, handleSubmitReviewCitationFixer, handleTickGBrainContradictionProbe,
    handleTickGBrainDreamCycle, handleUploadUpdateRelease, isSystemAccount, knowledgeReviews, knowledgeStatus, loadAdminData, newUser, openEditUser, openPasswordDialog,
    openUserMenuId, paginate, requestDeleteUser, requestRoleChange, requestStatusChange, reviewPage, reviewSearch, setAdminConfirm, setAdminTab, setAuditActionType,
    setAuditFilter, setAuditPage, setAuditSearch, setCitationFixerDraft, setGBrainContradictionDraft, setGBrainDreamDraft, setGBrainGraphDraft, setNewUser,
    setOpenUserMenuId, setReviewPage, setReviewSearch, setShowCreateUser, setTemplateSearch, setUpdateDraft, setUpdateFile, setUserGroupDrafts, setUserPage,
    setUserSearch, setUserSort, shortValue, showCreateUser, sortUsers, statusLabel, templateSearch, templates, uniqueAuditActions, updateDraft, updateFile, updateFileInputRef,
    updateReleases, userGroupDrafts, userPage, userSearch, userSort, yesNo, asRecord, recordNumber, recordText, toolResultArray, toolStatus,
  } = controller;
  return (
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

                    <AdminKnowledgeOverview
                      adminLoading={adminLoading}
                      formatDate={formatDate}
                      knowledgeStatus={knowledgeStatus}
                      statusLabel={statusLabel}
                      yesNo={yesNo}
                      onExportQualityReport={handleExportKnowledgeQualityReport}
                      onRefreshKnowledge={handleRefreshKnowledge}
                      onRestartGBrain={handleRestartGBrain}
                      onRunQualityReport={handleRunKnowledgeQualityReport}
                      onStartGBrain={handleStartGBrain}
                    />
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
                                    {isSystemAccount(item) ? <span>固定内置管理员</span> : null}
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
                  <KnowledgeReviewPanel
                    adminLoading={adminLoading}
                    formatDate={formatDate}
                    knowledgeReviews={knowledgeReviews}
                    reviewPage={reviewPage}
                    reviewSearch={reviewSearch}
                    setReviewPage={setReviewPage}
                    setReviewSearch={setReviewSearch}
                    onReviewKnowledge={handleReviewKnowledge}
                    onSubmitReviewCitationFixer={handleSubmitReviewCitationFixer}
                  />
                ) : null}

                {adminTab === "gbrain" ? (
                  <AdminGBrainSection controller={controller} />
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
  );
}
