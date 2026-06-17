import type { GBrainEntityMergeCandidate, WorkspaceKnowledgeGraphResponse } from "../../../shared/api/types";
import { MaximizeIcon, RefreshIcon, SearchIcon, XmarkIcon } from "../../../shared/icons/LineIcons";
import {
  crmEntityLabel,
  crmRelationLabel,
  crmShortSource,
  graphCanvasLabel,
  graphEntityTypeColor,
} from "../knowledgeGraphUtils";
import { buildWorkspaceKnowledgeGraphViewModel } from "../workspaceKnowledgeGraphViewModel";

type KnowledgeGraphViewModel = ReturnType<typeof buildWorkspaceKnowledgeGraphViewModel>;

export type WorkspaceCustomerIntelligenceOverlayProps = {
  canShowEntityMergeReview: boolean;
  closeKnowledgeGraph: () => void;
  entityMergeLoading: boolean;
  entityMergeMessage: string | null;
  graphEntityFilter: string;
  graphSearchTerm: string;
  graphTimelineFilter: "all" | "dated" | "undated" | "selected";
  handleApplyEntityMergeCandidate: (candidate: GBrainEntityMergeCandidate, action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes") => void | Promise<void>;
  handleLoadEntityMergeCandidates: () => void | Promise<void>;
  handleOpenKnowledgeGraph: () => void | Promise<void>;
  handlePreviewEntityMergeCandidate: (candidate: GBrainEntityMergeCandidate) => void | Promise<void>;
  knowledgeGraph: WorkspaceKnowledgeGraphResponse | null;
  knowledgeGraphError: string | null;
  knowledgeGraphLoading: boolean;
  knowledgeGraphOpen: boolean;
  openGraphSourcePreview: (sourcePath: string) => void | Promise<void>;
  resetKnowledgeGraphCanvasView: () => void;
  setGraphEntityFilter: (value: string) => void;
  setGraphSearchTerm: (value: string) => void;
  setGraphTimelineFilter: (value: "all" | "dated" | "undated" | "selected") => void;
  setKnowledgeGraphCanvasOpen: (open: boolean) => void;
  setSelectedGraphEventId: (id: string | null) => void;
  setSelectedGraphNodeId: (id: string | null) => void;
  selectedGraphEventId: string | null;
  selectedGraphNodeId: string | null;
  viewModel: KnowledgeGraphViewModel;
  workspaceName?: string;
};

export function WorkspaceCustomerIntelligenceOverlay({
  canShowEntityMergeReview,
  closeKnowledgeGraph,
  entityMergeLoading,
  entityMergeMessage,
  graphEntityFilter,
  graphSearchTerm,
  graphTimelineFilter,
  handleApplyEntityMergeCandidate,
  handleLoadEntityMergeCandidates,
  handleOpenKnowledgeGraph,
  handlePreviewEntityMergeCandidate,
  knowledgeGraph,
  knowledgeGraphError,
  knowledgeGraphLoading,
  knowledgeGraphOpen,
  openGraphSourcePreview,
  resetKnowledgeGraphCanvasView,
  setGraphEntityFilter,
  setGraphSearchTerm,
  setGraphTimelineFilter,
  setKnowledgeGraphCanvasOpen,
  setSelectedGraphEventId,
  setSelectedGraphNodeId,
  selectedGraphEventId,
  selectedGraphNodeId,
  viewModel,
  workspaceName,
}: WorkspaceCustomerIntelligenceOverlayProps) {
  if (!knowledgeGraphOpen) return null;
  const {
    crmCanvasEdges,
    crmCanvasNodes,
    crmCanvasPositions,
    crmCardReason,
    crmCompanyCount,
    crmDatedEventCount,
    crmLatestEvent,
    crmMostActiveContact,
    crmPersonCount,
    crmProjectCount,
    crmRecentEvents,
    crmRelationshipHub,
    crmSelectedEvents,
    crmSelectedRelations,
    crmVisibleProfileCards,
    filteredGraphEvents,
    filteredProfileCards,
    nodeTitleById,
    selectedGraphEvent,
    selectedGraphEventSourcePath,
    selectedGraphNode,
    selectedGraphNodeSourcePath,
    selectedNeighborIds,
    visibleEntityCandidates,
  } = viewModel;

  return (
    <div className="crm-intelligence-overlay" role="dialog" aria-modal="true" aria-label="CRM 客户情报">
      <section className="crm-intelligence-shell">
        <header className="crm-intelligence-header">
          <div>
            <span>CRM 客户情报</span>
            <strong>{workspaceName || "客户工作区"}</strong>
            <small>客户情报、关系网和近期互动来自受限客户情报数据。</small>
          </div>
          <div className="crm-intelligence-header-actions">
            <button disabled={knowledgeGraphLoading} onClick={() => void handleOpenKnowledgeGraph()} type="button"><RefreshIcon />刷新</button>
            <button disabled={crmCanvasNodes.length === 0} onClick={() => { resetKnowledgeGraphCanvasView(); setKnowledgeGraphCanvasOpen(true); }} type="button"><MaximizeIcon />大画布</button>
            <button aria-label="关闭 CRM 客户情报" onClick={closeKnowledgeGraph} type="button"><XmarkIcon /></button>
          </div>
        </header>
        <div className="crm-intelligence-toolbar">
          <label>
            <SearchIcon />
            <input
              onChange={(event) => setGraphSearchTerm(event.target.value)}
              placeholder="搜索客户、联系人、项目或事件"
              type="search"
              value={graphSearchTerm}
            />
          </label>
          <div>
            {[
              { value: "all", label: "全部" },
              { value: "customer_person_source_record", label: "联系人" },
              { value: "customer_company_source_record", label: "公司" },
              { value: "customer_project_source_record", label: "项目" },
            ].map((item) => (
              <button
                aria-pressed={graphEntityFilter === item.value}
                className={graphEntityFilter === item.value ? "is-active" : ""}
                key={item.value}
                onClick={() => setGraphEntityFilter(item.value)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        {knowledgeGraphLoading ? <p className="crm-intelligence-message">正在读取客户情报...</p> : null}
        {knowledgeGraphError ? <p className="crm-intelligence-message is-error">{knowledgeGraphError}</p> : null}
        {!knowledgeGraphLoading && knowledgeGraph ? (
          <div className="crm-intelligence-body">
            <aside className="crm-intelligence-roster">
              <section className="crm-intelligence-brief" aria-label="客户情报摘要">
                <div className="crm-intelligence-list-head">
                  <strong>这批资料能快速看到</strong>
                  <small>按互动和关系自动提取</small>
                </div>
                <div className="crm-intelligence-brief-list">
                  {crmMostActiveContact ? (
                    <button onClick={() => setSelectedGraphNodeId(crmMostActiveContact.id)} type="button">
                      <span>最活跃联系人</span>
                      <strong title={crmMostActiveContact.title}>{crmMostActiveContact.title}</strong>
                      <small>{crmMostActiveContact.event_count} 次互动 · {crmMostActiveContact.relation_count} 条关系</small>
                    </button>
                  ) : null}
                  {crmRelationshipHub ? (
                    <button onClick={() => setSelectedGraphNodeId(crmRelationshipHub.id)} type="button">
                      <span>关系中心</span>
                      <strong title={crmRelationshipHub.title}>{crmRelationshipHub.title}</strong>
                      <small>{crmEntityLabel(crmRelationshipHub.entity_type)} · 连接 {crmRelationshipHub.relation_count} 条关系</small>
                    </button>
                  ) : null}
                  {crmLatestEvent ? (
                    <button
                      onClick={() => {
                        setSelectedGraphNodeId(crmLatestEvent.entity_id);
                        setSelectedGraphEventId(crmLatestEvent.id);
                      }}
                      type="button"
                    >
                      <span>最近互动</span>
                      <strong title={crmLatestEvent.title}>{crmShortSource(crmLatestEvent.title)}</strong>
                      <small>{crmLatestEvent.date || "未标日期"} · {nodeTitleById.get(crmLatestEvent.entity_id) || "客户对象"}</small>
                    </button>
                  ) : null}
                  {!crmMostActiveContact && !crmRelationshipHub && !crmLatestEvent ? (
                    <p>当前筛选下还没有足够的关系或互动记录。</p>
                  ) : null}
                </div>
              </section>
              <div className="crm-intelligence-scope" aria-label="资料范围">
                <span><strong>{crmPersonCount}</strong><small>联系人</small></span>
                <span><strong>{crmCompanyCount}</strong><small>公司</small></span>
                <span><strong>{crmProjectCount}</strong><small>项目</small></span>
                <span><strong>{crmDatedEventCount}/{filteredGraphEvents.length}</strong><small>有日期互动</small></span>
              </div>
              <div className="crm-intelligence-list-head">
                <strong>可追踪对象</strong>
                <small>{crmVisibleProfileCards.length} / {filteredProfileCards.length}</small>
              </div>
              <div className="crm-intelligence-roster-list">
                {crmVisibleProfileCards.map((card) => (
                  <button
                    className={selectedGraphNodeId === card.id ? "is-selected" : ""}
                    key={card.id}
                    onClick={() => setSelectedGraphNodeId(card.id)}
                    type="button"
                  >
                    <span>{crmEntityLabel(card.entity_type)}</span>
                    <strong title={card.title}>{card.title}</strong>
                    <small>{crmCardReason(card)}</small>
                  </button>
                ))}
                {crmVisibleProfileCards.length === 0 ? <p>没有匹配的客户对象。</p> : null}
              </div>
            </aside>
            <main className="crm-intelligence-main">
              <section className="crm-intelligence-map-card">
                <div className="crm-intelligence-section-title">
                  <div>
                    <strong>关系网</strong>
                    <small>点击节点查看业务关系，默认只显示当前筛选下的关键对象。</small>
                  </div>
                  <span>{crmCanvasNodes.length} 节点 · {crmCanvasEdges.length} 关系</span>
                </div>
                <div className="crm-intelligence-map">
                  {crmCanvasNodes.length > 0 ? (
                    <svg viewBox="0 0 720 420" preserveAspectRatio="xMidYMid meet">
                      <defs>
                        <marker id="crm-intelligence-arrow" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
                          <path d="M0,0 L7,3 L0,6 Z" />
                        </marker>
                      </defs>
                      {crmCanvasEdges.map((edge) => {
                        const from = crmCanvasPositions.get(edge.from);
                        const to = crmCanvasPositions.get(edge.to);
                        if (!from || !to) return null;
                        const isActive = Boolean(selectedGraphNode && (edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id));
                        return (
                          <g className={isActive ? "is-active" : ""} key={edge.id}>
                            <line markerEnd="url(#crm-intelligence-arrow)" x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
                            <title>{`${nodeTitleById.get(edge.from) || edge.from} · ${crmRelationLabel(edge.relation_type)} · ${nodeTitleById.get(edge.to) || edge.to}`}</title>
                          </g>
                        );
                      })}
                      {crmCanvasNodes.map((node) => {
                        const point = crmCanvasPositions.get(node.id);
                        if (!point) return null;
                        const isSelected = selectedGraphNodeId === node.id;
                        const isNeighbor = selectedNeighborIds.has(node.id);
                        return (
                          <g
                            className={`${isSelected ? "is-selected" : ""} ${isNeighbor ? "is-neighbor" : ""}`}
                            key={node.id}
                            onClick={() => setSelectedGraphNodeId(node.id)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                setSelectedGraphNodeId(node.id);
                              }
                            }}
                            role="button"
                            tabIndex={0}
                            transform={`translate(${point.x} ${point.y})`}
                          >
                            <circle fill={graphEntityTypeColor(node.entity_type)} r={isSelected ? 25 : 20} />
                            <text textAnchor="middle" y="4">{graphCanvasLabel(node.title)}</text>
                            <title>{`${node.title} · ${crmEntityLabel(node.entity_type)}`}</title>
                          </g>
                        );
                      })}
                    </svg>
                  ) : (
                    <p>没有可展示的关系网。</p>
                  )}
                </div>
              </section>
              <section className="crm-intelligence-timeline-card">
                <div className="crm-intelligence-section-title">
                  <div>
                    <strong>近期互动</strong>
                    <small>事件可点击，右侧会显示对应详情和来源。</small>
                  </div>
                  <div className="crm-intelligence-timeline-tabs">
                    {[
                      { key: "all", label: "全部" },
                      { key: "dated", label: "有日期" },
                      { key: "selected", label: "当前对象" },
                    ].map((item) => (
                      <button
                        aria-pressed={graphTimelineFilter === item.key}
                        className={graphTimelineFilter === item.key ? "is-active" : ""}
                        disabled={item.key === "selected" && !selectedGraphNode}
                        key={item.key}
                        onClick={() => setGraphTimelineFilter(item.key as typeof graphTimelineFilter)}
                        type="button"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="crm-intelligence-timeline">
                  {crmRecentEvents.map((event) => (
                    <button
                      className={selectedGraphEventId === event.id ? "is-selected" : ""}
                      key={event.id}
                      onClick={() => {
                        setSelectedGraphNodeId(event.entity_id);
                        setSelectedGraphEventId(event.id);
                      }}
                      type="button"
                    >
                      <span>{event.date || "未标日期"}</span>
                      <strong title={event.title}>{crmShortSource(event.title)}</strong>
                      <small>{nodeTitleById.get(event.entity_id) || "客户对象"} · {crmShortSource(event.source_file)}</small>
                    </button>
                  ))}
                  {crmRecentEvents.length === 0 ? <p>没有匹配的互动记录。</p> : null}
                </div>
              </section>
            </main>
            <aside className="crm-intelligence-detail">
              {selectedGraphNode ? (
                <>
                  <div className="crm-intelligence-detail-head">
                    <span>{crmEntityLabel(selectedGraphNode.entity_type)}</span>
                    <strong title={selectedGraphNode.title}>{selectedGraphNode.title}</strong>
                    <small>{crmShortSource(selectedGraphNode.source_file || selectedGraphNode.file)}</small>
                  </div>
                  <div className="crm-intelligence-actions">
                    <button disabled={!selectedGraphNodeSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphNodeSourcePath)} type="button">查看来源</button>
                    {canShowEntityMergeReview ? (
                      <button disabled={entityMergeLoading} onClick={() => void handleLoadEntityMergeCandidates()} type="button">检查待确认实体</button>
                    ) : null}
                  </div>
                  <section>
                    <h3>业务关系</h3>
                    {crmSelectedRelations.map((edge) => {
                      const otherNodeId = edge.from === selectedGraphNode.id ? edge.to : edge.from;
                      return (
                        <button key={edge.id} onClick={() => setSelectedGraphNodeId(otherNodeId)} type="button">
                          <span>{crmRelationLabel(edge.relation_type)}</span>
                          <strong title={nodeTitleById.get(otherNodeId) || otherNodeId}>{nodeTitleById.get(otherNodeId) || otherNodeId}</strong>
                        </button>
                      );
                    })}
                    {crmSelectedRelations.length === 0 ? <p>暂无已识别关系。</p> : null}
                  </section>
                  <section>
                    <h3>相关互动</h3>
                    {crmSelectedEvents.map((event) => (
                      <button
                        className={selectedGraphEventId === event.id ? "is-selected" : ""}
                        key={event.id}
                        onClick={() => setSelectedGraphEventId(event.id)}
                        type="button"
                      >
                        <span>{event.date || "未标日期"}</span>
                        <strong title={event.title}>{crmShortSource(event.title)}</strong>
                      </button>
                    ))}
                    {crmSelectedEvents.length === 0 ? <p>暂无互动记录。</p> : null}
                  </section>
                  {selectedGraphEvent ? (
                    <section className="crm-intelligence-event-focus">
                      <h3>事件详情</h3>
                      <strong title={selectedGraphEvent.title}>{crmShortSource(selectedGraphEvent.title)}</strong>
                      <span>{selectedGraphEvent.date || "未标日期"}</span>
                      <small>{crmShortSource(selectedGraphEvent.source_file)}</small>
                      <button disabled={!selectedGraphEventSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphEventSourcePath)} type="button">打开事件来源</button>
                    </section>
                  ) : null}
                  {canShowEntityMergeReview ? (
                    <details className="crm-intelligence-admin">
                      <summary>管理员处理</summary>
                      {entityMergeMessage ? <p>{entityMergeMessage}</p> : null}
                      {visibleEntityCandidates.map((candidate) => (
                        <div key={candidate.id}>
                          <strong>{candidate.title}</strong>
                          <span>{crmEntityLabel(candidate.entity_type)} · {Math.round((candidate.confidence ?? 0) * 100)}%</span>
                          <button disabled={entityMergeLoading} onClick={() => void handlePreviewEntityMergeCandidate(candidate)} type="button">预览</button>
                          <button disabled={entityMergeLoading} onClick={() => void handleApplyEntityMergeCandidate(candidate, "dismiss")} type="button">忽略</button>
                        </div>
                      ))}
                      {visibleEntityCandidates.length === 0 ? <button disabled={entityMergeLoading} onClick={() => void handleLoadEntityMergeCandidates()} type="button">加载待确认实体</button> : null}
                    </details>
                  ) : null}
                </>
              ) : (
                <p>请选择一个客户、联系人或项目。</p>
              )}
            </aside>
          </div>
        ) : null}
      </section>
    </div>
  );
}
