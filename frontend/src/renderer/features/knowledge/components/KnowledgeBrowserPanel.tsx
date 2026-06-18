import { useEffect, useMemo, useState } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import type {
  KnowledgeSearchResultResponse,
  KnowledgeSourceScopeResponse,
  WorkspaceResponse,
} from "../../../shared/api/types";
import { SearchIcon } from "../../../shared/icons/LineIcons";
import { knowledgeScopeForWorkspace } from "../knowledgeScope";
import { listKnowledgeSources, searchKnowledge } from "../api";

export type KnowledgeBrowserPanelProps = {
  apiOptions: ApiClientOptions;
  workspace?: WorkspaceResponse | null;
  workspaceId?: number | null;
  onClose: () => void;
  onUseQuery: (query: string) => void;
};

export function KnowledgeBrowserPanel({
  apiOptions,
  workspace,
  workspaceId,
  onClose,
  onUseQuery,
}: KnowledgeBrowserPanelProps) {
  const [query, setQuery] = useState("");
  const [sourceScope, setSourceScope] = useState("all");
  const [scopes, setScopes] = useState<KnowledgeSourceScopeResponse[]>([]);
  const [results, setResults] = useState<KnowledgeSearchResultResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const scopeInfo = useMemo(() => knowledgeScopeForWorkspace(workspace), [workspace]);

  useEffect(() => {
    let mounted = true;
    setError("");
    listKnowledgeSources(apiOptions, workspaceId)
      .then((response) => {
        if (!mounted) return;
        setScopes(response.scopes);
        setSourceScope(response.scopes.length > 1 ? "all" : response.scopes[0]?.scope ?? "all");
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setScopes([]);
        setError(err instanceof Error ? err.message : "无法读取知识库范围");
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions, workspaceId]);

  async function handleSearch() {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await searchKnowledge(apiOptions, trimmed, {
        workspaceId,
        sourceScope,
        limit: 12,
      });
      setResults(response.results);
    } catch (err) {
      setResults([]);
      setError(err instanceof Error ? err.message : "知识库搜索失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="utility-side-pane auxiliary-side-pane knowledge-browser-pane" aria-label="知识库浏览">
      <header className="utility-side-header">
        <div>
          <h2>知识库</h2>
          <p>{scopeInfo.scopeLabel}</p>
        </div>
        <button className="prompt-panel-close" onClick={onClose} type="button">×</button>
      </header>

      <div className="knowledge-browser-body">
        <div className="knowledge-browser-scope-card">
          <strong>检索范围</strong>
          <p>{scopeInfo.riskNote}</p>
          <div className="knowledge-browser-scope-list">
            {scopes.map((scope) => (
              <span key={`${scope.scope}-${scope.source_id || "empty"}`}>
                {scope.label}
              </span>
            ))}
          </div>
        </div>

        <div className="knowledge-browser-search">
          <SearchIcon />
          <input
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void handleSearch();
            }}
            placeholder="搜索公司制度、项目资料或客户情报"
            value={query}
          />
          <button disabled={loading || !query.trim()} onClick={() => void handleSearch()} type="button">
            {loading ? "搜索中" : "搜索"}
          </button>
        </div>

        {scopes.length > 1 ? (
          <div className="knowledge-browser-filters" aria-label="知识库来源过滤">
            <button className={sourceScope === "all" ? "is-active" : ""} onClick={() => setSourceScope("all")} type="button">全部</button>
            {scopes.map((scope) => (
              <button
                className={sourceScope === scope.scope ? "is-active" : ""}
                key={scope.scope}
                onClick={() => setSourceScope(scope.scope)}
                type="button"
              >
                {scope.label}
              </button>
            ))}
          </div>
        ) : null}

        {error ? <p className="knowledge-browser-error">{error}</p> : null}
        {!error && results.length === 0 ? (
          <div className="knowledge-browser-empty">
            {query.trim() ? "暂无匹配结果，可换一个关键词或直接发起 /query。" : "输入关键词后，可独立搜索当前可用知识范围。"}
          </div>
        ) : null}

        <div className="knowledge-browser-results">
          {results.map((result, index) => (
            <article className="knowledge-browser-result" key={`${result.scope}-${result.file}-${result.section_path ?? index}`}>
              <div className="knowledge-browser-result-meta">
                <span>{scopeLabel(result.scope)}</span>
                {result.type ? <small>{result.type}</small> : null}
              </div>
              <h3>{result.title}</h3>
              {result.section_path ? <p className="knowledge-browser-path">{result.section_path}</p> : null}
              <p>{result.excerpt || "该结果未返回可展示片段。"}</p>
              <footer>
                <code>{result.source_id ?? result.file}</code>
                <button onClick={() => onUseQuery(query.trim())} type="button">用 /query 追问</button>
              </footer>
            </article>
          ))}
        </div>
      </div>
    </aside>
  );
}

function scopeLabel(scope: string) {
  if (scope === "project") return "项目";
  if (scope === "customer") return "客户";
  return "公司";
}
