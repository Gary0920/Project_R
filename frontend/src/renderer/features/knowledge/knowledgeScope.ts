import type { WorkspaceResponse } from "../../shared/api/types";

export type KnowledgeScopeInfo = {
  excludedScopes: string[];
  includedScopes: string[];
  riskNote: string;
  scopeLabel: string;
  workspaceKind: string;
};

export function knowledgeScopeForWorkspace(workspace?: WorkspaceResponse | null): KnowledgeScopeInfo {
  const kind = String(workspace?.workspace_kind ?? "user");
  if (kind === "customer") {
    return {
      excludedScopes: ["公司知识", "项目资料"],
      includedScopes: ["当前客户情报"],
      riskNote: "客户工作区只查询当前客户情报，不叠加公司知识或项目资料。",
      scopeLabel: "当前客户情报",
      workspaceKind: kind,
    };
  }
  if (kind === "project") {
    return {
      excludedScopes: ["客户情报", "其他项目资料"],
      includedScopes: ["公司知识", workspace?.name ? `当前项目资料：${workspace.name}` : "当前项目资料"],
      riskNote: "项目工作区会叠加公司知识与当前项目资料，不查询客户情报或其他项目。",
      scopeLabel: "公司知识 + 当前项目资料",
      workspaceKind: kind,
    };
  }
  return {
    excludedScopes: ["项目资料", "客户情报"],
    includedScopes: ["公司知识"],
    riskNote: "个人工作台只查询公司知识，不查询项目资料或客户情报。",
    scopeLabel: "公司知识",
    workspaceKind: kind,
  };
}

export function isKnowledgeQueryDraft(draft: string, selectedBuiltinCommand?: { name?: string | null } | null) {
  const text = draft.trimStart().toLowerCase();
  return selectedBuiltinCommand?.name === "query" || text === "/query" || text.startsWith("/query ");
}
