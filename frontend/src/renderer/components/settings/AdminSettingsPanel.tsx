import { useState, type ReactNode } from "react";

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
} from "../../api/types";
import { ChevronDownIcon, EditIcon, MoreIcon, SearchIcon, ShieldIcon } from "../LineIcons";

type AdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type AdminUserRole = "admin" | "employee";
type AdminComboOption = {
  value: string;
  label: string;
  meta?: string;
  badge?: string;
  disabled?: boolean;
};

type DraftSetter<T> = { bivarianceHack(value: T | ((prev: T) => T)): void }["bivarianceHack"];
type AnyRecord = Record<string, any>;

export type AdminSettingsPanelController = {
  adminGroupOptions: AdminComboOption[];
  adminLoading: boolean;
  adminMessage: string;
  adminTab: AdminTab;
  adminUserSearchOptions: AdminComboOption[];
  adminUsers: AdminUserResponse[];
  auditActionType: string;
  auditFilter: AnyRecord;
  auditLogs: AuditLogResponse[];
  auditPage: number;
  auditSearch: string;
  citationFixerDraft: AnyRecord;
  currentUser: CurrentUserResponse | null;
  filterAuditLogs: (logs: AuditLogResponse[], search: string, actionType: string) => AuditLogResponse[];
  filterReviews: (reviews: KnowledgeReviewResponse[], search: string) => KnowledgeReviewResponse[];
  filterTemplates: (templates: AdminTemplateStatusResponse["items"], search: string) => AdminTemplateStatusResponse["items"];
  filterUsers: (users: AdminUserResponse[], search: string) => AdminUserResponse[];
  formatDate: (value: string | number) => string;
  formatFileSize: (bytes: number) => string;
  formatOptionalDate: (value?: string | null) => string;
  gbrainContradictionDraft: AnyRecord;
  gbrainDreamDraft: AnyRecord;
  gbrainEntityMerge: GBrainEntityMergeCandidatesResponse | null;
  gbrainEntityMergePreview: GBrainEntityMergePreviewResponse | null;
  gbrainGraph: GBrainGraphResponse | null;
  gbrainGraphDraft: AnyRecord;
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
  handleReviewKnowledge: (item: KnowledgeReviewResponse, status: "approved" | "rejected") => Promise<void>;
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
  newUser: AnyRecord;
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
  setAuditFilter: DraftSetter<AnyRecord>;
  setAuditPage: DraftSetter<number>;
  setAuditSearch: DraftSetter<string>;
  setCitationFixerDraft: DraftSetter<AnyRecord>;
  setGBrainContradictionDraft: DraftSetter<AnyRecord>;
  setGBrainDreamDraft: DraftSetter<AnyRecord>;
  setGBrainGraphDraft: DraftSetter<AnyRecord>;
  setNewUser: DraftSetter<AnyRecord>;
  setOpenUserMenuId: DraftSetter<number | null>;
  setReviewPage: DraftSetter<number>;
  setReviewSearch: DraftSetter<string>;
  setShowCreateUser: DraftSetter<boolean>;
  setTemplateSearch: DraftSetter<string>;
  setUpdateDraft: DraftSetter<AnyRecord>;
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
  updateDraft: AnyRecord;
  updateFile: File | null;
  updateFileInputRef: React.RefObject<HTMLInputElement | null>;
  updateReleases: ClientUpdateInfo[];
  userGroupDrafts: Record<number, string>;
  userPage: number;
  userSearch: string;
  userSort: { field: "username" | "created_at"; dir: "asc" | "desc" };
  yesNo: (value?: boolean | null) => string;
  asRecord: (value: unknown) => Record<string, unknown> | null;
  recordNumber: (record: Record<string, unknown> | null | undefined, key: string) => number | null;
  recordText: (record: Record<string, unknown> | null | undefined, key: string) => string;
  canSubmitReviewCitationFixer: (item: KnowledgeReviewResponse) => boolean;
  toolResultArray: (response?: GBrainToolResponse | null, nestedKey?: string) => Array<Record<string, unknown>>;
  toolStatus: (response?: GBrainToolResponse | null) => string;
};

export type AdminSettingsPanelProps = {
  controller: AdminSettingsPanelController;
};

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

export function AdminSettingsPanel({ controller }: AdminSettingsPanelProps) {
  const {
    adminGroupOptions, adminLoading, adminMessage, adminTab, adminUserSearchOptions, adminUsers, auditActionType, auditFilter, auditLogs, auditPage, auditSearch,
    citationFixerDraft, currentUser, filterAuditLogs, filterReviews, filterTemplates, filterUsers,
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
    updateReleases, userGroupDrafts, userPage, userSearch, userSort, yesNo, asRecord, recordNumber, recordText, canSubmitReviewCitationFixer, toolResultArray, toolStatus,
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
  );
}
