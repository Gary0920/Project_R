import type { Workspace } from "./state";

export function getWorkspaceAffiliationLabel(workspace: Workspace | undefined) {
  if (!workspace) return "未选择";
  if (workspace.workspace_kind === "user") return "个人";
  if (workspace.workspace_kind === "customer") return "CRM";
  if (workspace.is_default) return "私人";
  if (workspace.is_hidden) return "隐藏";
  return workspace.brand || "项目";
}

export function getWorkspaceAffiliationPath(workspace: Workspace | undefined) {
  if (!workspace) return "未选择工作区";
  const name = String(workspace.name || "未命名工作区").trim();
  if (workspace.workspace_kind === "user") return `个人 / ${name}`;
  if (workspace.workspace_kind === "customer") return `CRM / ${name}`;
  const brand = String(workspace.brand || "项目").trim() || "项目";
  return `${brand} / ${name}`;
}
