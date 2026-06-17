import { useEffect, useMemo, useRef, useState } from "react";

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
} from "../../admin/api";
import { listClientUpdateReleases, uploadClientUpdateRelease } from "../../updates/api";
import { ApiError, type ApiClientOptions } from "../../../shared/api/client";
import { parseApiDate } from "../../../shared/utils/time";
import type {
  AdminGroupCandidateResponse,
  AdminTemplateStatusResponse,
  AdminUserCandidateResponse,
  AdminUserResponse,
  AuditLogResponse,
  ClientUpdateInfo,
  CurrentUserResponse,
  GBrainEntityMergeCandidate,
  GBrainEntityMergeCandidatesResponse,
  GBrainEntityMergePreviewResponse,
  GBrainMaintenanceResponse,
  GBrainGraphResponse,
  KnowledgeReviewResponse,
  KnowledgeStatusResponse,
} from "../../../shared/api/types";
import type { AdminSettingsPanelController } from "../../admin/components/AdminSettingsPanel";
import type { AdminComboOption } from "../components/AdminComboInput";
import {
  asRecord,
  generateTemporaryPassword,
  isSystemAccount,
  recordNumber,
  recordText,
  roleLabel,
  shortValue,
  statusLabel,
  toolResultArray,
  toolStatus,
  userDisplayName,
  yesNo,
  type AdminPasswordDialogState,
  type AdminUserConfirmState,
  type AdminUserRole,
} from "../settingsAdminHelpers";
import { formatDate, formatFileSize, formatOptionalDate } from "../settingsPreferences";

const CUSTOMER_INTELLIGENCE_SOURCE_ID = "customer-crm";

export type AdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";

type UseSettingsAdminControllerOptions = {
  activeSection: string;
  apiOptions: ApiClientOptions;
  currentUser: CurrentUserResponse | null;
  isOpen: boolean;
  refreshCurrentUser: (user: CurrentUserResponse) => void;
};

export function useSettingsAdminController({
  activeSection,
  apiOptions,
  currentUser,
  isOpen,
  refreshCurrentUser,
}: UseSettingsAdminControllerOptions) {
  const updateFileInputRef = useRef<HTMLInputElement>(null);
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
    if (!isOpen || activeSection !== "admin" || adminTab !== "users") return;
    const handle = window.setTimeout(() => {
      listAdminUserCandidates(apiOptions, userSearch, 30)
        .then(setAdminUserCandidates)
        .catch(() => setAdminUserCandidates([]));
    }, 160);
    return () => window.clearTimeout(handle);
  }, [activeSection, adminTab, apiOptions, isOpen, userSearch]);

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
  }, [activeSection, currentUser?.role, apiOptions]);

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

  async function handleReviewKnowledge(item: KnowledgeReviewResponse, status: "approved" | "rejected", content?: string) {
    try {
      await reviewKnowledge(apiOptions, item.id, status, status === "approved" ? content : undefined);
      await loadAdminData();
      return true;
    } catch (error) {
      setAdminMessage(error instanceof ApiError ? error.message : "知识审核失败。");
      return false;
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

  const controller: AdminSettingsPanelController = {
    adminGroupOptions, adminLoading, adminMessage, adminTab, adminUserSearchOptions, adminUsers, auditActionType, auditFilter, auditLogs, auditPage, auditSearch,
    citationFixerDraft, currentUser, filterAuditLogs, filterTemplates, filterUsers, formatDate, formatFileSize, formatOptionalDate, gbrainContradictionDraft,
    gbrainDreamDraft, gbrainEntityMerge, gbrainEntityMergePreview, gbrainGraph, gbrainGraphDraft, gbrainMaintenance, handleApplyGBrainEntityMergeCandidate,
    handleCancelGBrainJob, handleCreateUser, handleExportKnowledgeQualityReport, handleGBrainMaintenanceCheck, handleLoadGBrainEntityMergeCandidates,
    handleLoadGBrainGraph, handlePollGBrainCitationFixerJobs, handlePollGBrainDreamCycleJobs, handlePreviewGBrainEntityMergeCandidate, handleRefreshGBrainMaintenance,
    handleRefreshKnowledge, handleRestartGBrain, handleRestartGBrainDreamCycleWorker, handleRetryGBrainJob, handleReviewKnowledge, handleRollbackGBrainCitationFixerJob,
    handleRunGBrainContradictionProbe, handleRunGBrainDreamCycle, handleRunKnowledgeQualityReport, handleSaveGBrainContradictionProbe, handleSaveGBrainDreamCycle,
    handleSaveUserGroup, handleStartGBrain, handleSubmitCitationFixer, handleSubmitGBrainJob, handleSubmitReviewCitationFixer, handleTickGBrainContradictionProbe,
    handleTickGBrainDreamCycle, handleUploadUpdateRelease, isSystemAccount, knowledgeReviews, knowledgeStatus, loadAdminData, newUser, openEditUser, openPasswordDialog,
    openUserMenuId, paginate, requestDeleteUser, requestRoleChange, requestStatusChange, reviewPage, reviewSearch, setAdminConfirm, setAdminTab, setAuditActionType,
    setAuditFilter, setAuditPage, setAuditSearch, setCitationFixerDraft, setGBrainContradictionDraft, setGBrainDreamDraft, setGBrainGraphDraft, setNewUser,
    setOpenUserMenuId, setReviewPage, setReviewSearch, setShowCreateUser, setTemplateSearch, setUpdateDraft, setUpdateFile, setUserGroupDrafts, setUserPage,
    setUserSearch, setUserSort, shortValue, showCreateUser, sortUsers, statusLabel, templateSearch, templates, uniqueAuditActions, updateDraft, updateFile,
    updateFileInputRef, updateReleases, userGroupDrafts, userPage, userSearch, userSort, yesNo, asRecord, recordNumber, recordText, toolResultArray, toolStatus,
  };

  return {
    adminConfirm,
    controller,
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
  };
}
