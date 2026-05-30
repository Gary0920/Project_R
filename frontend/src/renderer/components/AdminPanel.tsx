import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useState } from "react";

import {
  createAdminUser,
  listAdminTemplates,
  listAdminUsers,
  listAuditLogs,
  listKnowledgeReviews,
  getKnowledgeStatus,
  refreshKnowledge,
  resetAdminUserPassword,
  reviewKnowledge,
  updateAdminUser,
} from "../api/admin";
import { ApiError } from "../api/client";
import type {
  AdminTemplateStatusResponse,
  AdminUserResponse,
  AuditLogResponse,
  KnowledgeReviewResponse,
  KnowledgeStatusResponse,
} from "../api/types";
import { authTokenAtom, clearAuthAtom } from "../atoms/auth-atoms";
import { serverUrlAtom } from "../atoms/server-atoms";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export type AdminPanelProps = {
  isOpen: boolean;
  onClose: () => void;
};

export function AdminPanel({ isOpen, onClose }: AdminPanelProps) {
  const serverUrl = useAtomValue(serverUrlAtom);
  const token = useAtomValue(authTokenAtom);
  const clearAuth = useSetAtom(clearAuthAtom);
  const [adminUsers, setAdminUsers] = useState<AdminUserResponse[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogResponse[]>([]);
  const [knowledgeReviews, setKnowledgeReviews] = useState<KnowledgeReviewResponse[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatusResponse | null>(null);
  const [templates, setTemplates] = useState<AdminTemplateStatusResponse["items"]>([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminMessage, setAdminMessage] = useState("");
  const [newUser, setNewUser] = useState({ username: "", nickname: "", password: "", role: "employee" });
  const [auditFilter, setAuditFilter] = useState({ userId: "", dateFrom: "", dateTo: "" });

  const apiOptions = { baseUrl: serverUrl, token, onUnauthorized: clearAuth };

  useEffect(() => {
    if (!isOpen) return;
    void loadAdminData();
  }, [isOpen, serverUrl, token]);

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

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card admin-panel-card" onClick={(event) => event.stopPropagation()}>
        <button className="modal-close" onClick={onClose} title="关闭" type="button">×</button>
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
              <button className="ghost-button" onClick={() => void handleRefreshKnowledge()} type="button">
                刷新索引
              </button>
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
      </div>
    </div>
  );
}
