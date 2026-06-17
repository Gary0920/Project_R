import type { WorkspaceResponse } from "../../../shared/api/types";
import { knowledgeScopeForWorkspace } from "../knowledgeScope";

export type KnowledgeScopeIndicatorProps = {
  active: boolean;
  workspace?: WorkspaceResponse | null;
};

export function KnowledgeScopeIndicator({ active, workspace }: KnowledgeScopeIndicatorProps) {
  if (!active) return null;
  const scope = knowledgeScopeForWorkspace(workspace);
  return (
    <section className="knowledge-scope-indicator" aria-label="知识库查询范围">
      <div className="knowledge-scope-main">
        <span className="knowledge-scope-kicker">知识库查询范围</span>
        <strong>{scope.scopeLabel}</strong>
      </div>
      <div className="knowledge-scope-detail">
        <span>将查询：{scope.includedScopes.join("、")}</span>
        <span>不会查询：{scope.excludedScopes.join("、")}</span>
      </div>
      <p>{scope.riskNote}</p>
    </section>
  );
}
