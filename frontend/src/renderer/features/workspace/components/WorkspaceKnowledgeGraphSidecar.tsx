import type { Dispatch, MouseEvent, SetStateAction } from "react";

import type {
  GBrainEntityMergeCandidate,
  GBrainEntityMergePreviewResponse,
  WorkspaceEntityMergeCandidatesResponse,
  WorkspaceKnowledgeGraphResponse,
  WorkspaceNativeGraphContextResponse,
} from "../../../shared/api/types";
import { MaximizeIcon, XmarkIcon } from "../../../shared/icons/LineIcons";
import {
  graphCanvasLabel,
  graphCitationString,
  graphEntityTypeColor,
  graphEventTimestamp,
} from "../knowledgeGraphUtils";
import { buildWorkspaceKnowledgeGraphViewModel, type GraphTimelineDensity, type GraphTimelineFilter } from "../workspaceKnowledgeGraphViewModel";

type KnowledgeGraphViewModel = ReturnType<typeof buildWorkspaceKnowledgeGraphViewModel>;

export type WorkspaceKnowledgeGraphSidecarProps = {
  canShowEntityMergeReview: boolean;
  closeKnowledgeGraph: () => void;
  collapsedTimelineGroups: Set<string>;
  collapseAllTimelineGroups: (labels: string[]) => void;
  entityMergeCandidates: WorkspaceEntityMergeCandidatesResponse | null;
  entityMergeLoading: boolean;
  entityMergeMessage: string | null;
  entityMergePreview: GBrainEntityMergePreviewResponse | null;
  expandAllTimelineGroups: () => void;
  filePreviewOpen: boolean;
  graphEntityFilter: string;
  graphSearchTerm: string;
  graphTimelineDensity: GraphTimelineDensity;
  graphTimelineFilter: GraphTimelineFilter;
  handleApplyEntityMergeCandidate: (candidate: GBrainEntityMergeCandidate, action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes") => void | Promise<void>;
  handleLoadEntityMergeCandidates: () => void | Promise<void>;
  handleLoadNativeGraphContext: (slug: string) => void | Promise<void>;
  handlePreviewEntityMergeCandidate: (candidate: GBrainEntityMergeCandidate) => void | Promise<void>;
  handlePreviewResizeStart: (event: MouseEvent<HTMLDivElement>) => void;
  isCustomerWorkspace: boolean;
  knowledgeGraph: WorkspaceKnowledgeGraphResponse | null;
  knowledgeGraphError: string | null;
  knowledgeGraphLabel: string;
  knowledgeGraphLoading: boolean;
  knowledgeGraphOpen: boolean;
  nativeGraphContext: WorkspaceNativeGraphContextResponse | null;
  nativeGraphLoadingSlug: string | null;
  nativeGraphMessage: string | null;
  openGraphSourcePreview: (sourcePath: string) => void | Promise<void>;
  previewResizing: boolean;
  resetKnowledgeGraphCanvasView: () => void;
  selectedGraphEventId: string | null;
  selectedGraphNodeId: string | null;
  setGraphEntityFilter: (value: string) => void;
  setGraphSearchTerm: (value: string) => void;
  setGraphTimelineDensity: Dispatch<SetStateAction<GraphTimelineDensity>>;
  setGraphTimelineFilter: (value: GraphTimelineFilter) => void;
  setKnowledgeGraphCanvasOpen: (open: boolean) => void;
  setKnowledgeGraphError: (message: string | null) => void;
  setSelectedGraphEventId: (id: string | null) => void;
  setSelectedGraphNodeId: (id: string | null) => void;
  standaloneCustomerIntelligence: boolean;
  toggleTimelineGroup: (label: string) => void;
  viewModel: KnowledgeGraphViewModel;
  workspaceName?: string;
};

export function WorkspaceKnowledgeGraphSidecar({
  canShowEntityMergeReview,
  closeKnowledgeGraph,
  collapsedTimelineGroups,
  collapseAllTimelineGroups,
  entityMergeCandidates,
  entityMergeLoading,
  entityMergeMessage,
  entityMergePreview,
  expandAllTimelineGroups,
  filePreviewOpen,
  graphEntityFilter,
  graphSearchTerm,
  graphTimelineDensity,
  graphTimelineFilter,
  handleApplyEntityMergeCandidate,
  handleLoadEntityMergeCandidates,
  handleLoadNativeGraphContext,
  handlePreviewEntityMergeCandidate,
  handlePreviewResizeStart,
  isCustomerWorkspace,
  knowledgeGraph,
  knowledgeGraphError,
  knowledgeGraphLabel,
  knowledgeGraphLoading,
  knowledgeGraphOpen,
  nativeGraphContext,
  nativeGraphLoadingSlug,
  nativeGraphMessage,
  openGraphSourcePreview,
  previewResizing,
  resetKnowledgeGraphCanvasView,
  selectedGraphEventId,
  selectedGraphNodeId,
  setGraphEntityFilter,
  setGraphSearchTerm,
  setGraphTimelineDensity,
  setGraphTimelineFilter,
  setKnowledgeGraphCanvasOpen,
  setKnowledgeGraphError,
  setSelectedGraphEventId,
  setSelectedGraphNodeId,
  standaloneCustomerIntelligence,
  toggleTimelineGroup,
  viewModel,
  workspaceName,
}: WorkspaceKnowledgeGraphSidecarProps) {
  if (!knowledgeGraphOpen || filePreviewOpen || isCustomerWorkspace || standaloneCustomerIntelligence) return null;

  const {
    canvasGraphEdges,
    canvasGraphNodes,
    canvasGraphPositions,
    filteredGraphEdges,
    filteredProfileCards,
    graphDegreeById,
    graphEntityTypes,
    nativeContextSections,
    nativeCounts,
    nodeTitleById,
    selectedGraphEvent,
    selectedGraphEventSourcePath,
    selectedGraphNode,
    selectedGraphNodeEdges,
    selectedGraphNodeEvents,
    selectedGraphNodeSourcePath,
    selectedNeighborIds,
    timelineGroupLabels,
    timelineGroups,
    timelineHiddenCount,
    visibleEntityCandidates,
  } = viewModel;

  return (
      <aside className={`workspace-file-preview-sidecar is-knowledge ${previewResizing ? "is-resizing" : ""}`} aria-label={knowledgeGraphLabel}>
        <div
          aria-label="调整图谱面板宽度"
          aria-orientation="vertical"
          className="workspace-file-preview-resize-handle"
          onMouseDown={handlePreviewResizeStart}
          role="separator"
          title="拖动调整图谱面板宽度"
        />
        <header className="workspace-file-preview-sidecar-header">
          <div>
            <strong>{knowledgeGraphLabel}</strong>
            <span>{knowledgeGraph?.source_id || workspaceName || "当前工作区"}</span>
          </div>
          <button aria-label={`关闭${knowledgeGraphLabel}`} className="workspace-file-action" onClick={closeKnowledgeGraph} title="关闭" type="button"><XmarkIcon /></button>
        </header>
        <div className="workspace-knowledge-graph-panel">
          {knowledgeGraphLoading ? <p className="agent-file-panel-note">正在读取 GBrain 图谱...</p> : null}
          {knowledgeGraphError ? <p className="agent-file-panel-note is-error"><span>{knowledgeGraphError}</span><button onClick={() => setKnowledgeGraphError(null)} type="button">关闭</button></p> : null}
          {!knowledgeGraphLoading && knowledgeGraph ? (
            <>
              <div className="workspace-knowledge-graph-stats">
                <span><strong>{knowledgeGraph.stats?.nodes ?? knowledgeGraph.nodes.length}</strong><small>实体</small></span>
                <span><strong>{knowledgeGraph.stats?.edges ?? knowledgeGraph.edges.length}</strong><small>关系</small></span>
                <span><strong>{knowledgeGraph.stats?.events ?? knowledgeGraph.events.length}</strong><small>事件</small></span>
              </div>
              <div className="workspace-knowledge-graph-filters" aria-label="图谱筛选">
                <label>
                  <span>搜索</span>
                  <input
                    onChange={(event) => setGraphSearchTerm(event.target.value)}
                    placeholder="实体、关系、事件或来源"
                    type="search"
                    value={graphSearchTerm}
                  />
                </label>
                <label>
                  <span>类型</span>
                  <select onChange={(event) => setGraphEntityFilter(event.target.value)} value={graphEntityFilter}>
                    <option value="all">全部实体</option>
                    {graphEntityTypes.map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </label>
                {(graphSearchTerm || graphEntityFilter !== "all") ? (
                  <button onClick={() => { setGraphSearchTerm(""); setGraphEntityFilter("all"); }} type="button">重置</button>
                ) : null}
              </div>
              <section className="workspace-knowledge-graph-section">
                <h3>{isCustomerWorkspace ? "画像记忆" : "关键节点"}</h3>
                {filteredProfileCards.length > 0 ? (
                  <div className="workspace-knowledge-card-list">
                    {filteredProfileCards.map((card) => (
                      <article className={`workspace-knowledge-card ${selectedGraphNodeId === card.id ? "is-selected" : ""}`} key={card.id}>
                        <div>
                          <strong>{card.title}</strong>
                          <span>{card.entity_type}</span>
                          <small>{card.relation_count} 条关系 · {card.event_count} 个事件</small>
                        </div>
                        <div className="workspace-knowledge-card-actions">
                          <button onClick={() => setSelectedGraphNodeId(card.id)} type="button">详情</button>
                          <button disabled={nativeGraphLoadingSlug === card.id} onClick={() => void handleLoadNativeGraphContext(card.id)} type="button">
                            {nativeGraphLoadingSlug === card.id ? "读取..." : isCustomerWorkspace ? "支撑信息" : "原生"}
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="workspace-knowledge-empty">暂无可展示的画像节点。</p>
                )}
              </section>
              <section className="workspace-knowledge-graph-section">
                <div className="workspace-knowledge-section-header">
                  <h3>{isCustomerWorkspace ? "关系网" : "事件关系图"}</h3>
                  <div className="workspace-knowledge-section-actions">
                    <small className="workspace-knowledge-section-meta">{canvasGraphNodes.length} 节点 · {canvasGraphEdges.length} 边</small>
                    <button disabled={canvasGraphNodes.length === 0} onClick={() => { resetKnowledgeGraphCanvasView(); setKnowledgeGraphCanvasOpen(true); }} title="打开大画布" type="button">
                      <MaximizeIcon />大画布
                    </button>
                  </div>
                </div>
                {canvasGraphNodes.length > 0 ? (
                  <div className="workspace-knowledge-canvas" aria-label={`${knowledgeGraphLabel}画布`} role="img">
                    <svg viewBox="0 0 340 216" preserveAspectRatio="xMidYMid meet">
                      <defs>
                        <marker id="workspace-graph-arrow" markerHeight="5" markerWidth="6" orient="auto" refX="5" refY="2.5">
                          <path d="M0,0 L6,2.5 L0,5 Z" />
                        </marker>
                      </defs>
                      {canvasGraphEdges.map((edge) => {
                        const from = canvasGraphPositions.get(edge.from);
                        const to = canvasGraphPositions.get(edge.to);
                        if (!from || !to) return null;
                        const isActive = Boolean(selectedGraphNode && (edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id));
                        return (
                          <g className={`workspace-knowledge-canvas-edge ${isActive ? "is-active" : ""}`} key={edge.id}>
                            <line markerEnd="url(#workspace-graph-arrow)" x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
                            <title>{`${nodeTitleById.get(edge.from) || edge.from} -> ${edge.relation_type} -> ${nodeTitleById.get(edge.to) || edge.to}`}</title>
                          </g>
                        );
                      })}
                      {canvasGraphNodes.map((node) => {
                        const point = canvasGraphPositions.get(node.id);
                        if (!point) return null;
                        const isSelected = selectedGraphNodeId === node.id;
                        const degree = graphDegreeById.get(node.id) ?? 0;
                        const maxDegree = Math.max(1, ...canvasGraphNodes.map((n) => graphDegreeById.get(n.id) ?? 0));
                        const degreeRadius = 16 + Math.min(12, (degree / maxDegree) * 12);
                        const nodeRadius = isSelected ? degreeRadius + 4 : degreeRadius;
                        const isNeighbor = selectedNeighborIds.has(node.id);
                        return (
                          <g
                            className={`workspace-knowledge-canvas-node ${isSelected ? "is-selected" : ""} ${isNeighbor ? "is-neighbor" : ""}`}
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
                            <circle fill={graphEntityTypeColor(node.entity_type)} r={nodeRadius} />
                            <text textAnchor="middle" y="4">{graphCanvasLabel(node.title)}</text>
                            <title>{`${node.title} · ${node.entity_type}`}</title>
                          </g>
                        );
                      })}
                    </svg>
                    <div className="workspace-knowledge-canvas-legend">
                      <span>点击节点查看详情</span>
                      {selectedGraphNode ? <strong title={selectedGraphNode.title}>{selectedGraphNode.title}</strong> : null}
                    </div>
                  </div>
                ) : (
                  <p className="workspace-knowledge-empty">暂无可绘制的图谱节点。</p>
                )}
              </section>
              {selectedGraphNode ? (
                <section className="workspace-knowledge-graph-section">
                  <div className="workspace-knowledge-section-header">
                    <h3>节点详情</h3>
                    <div className="workspace-knowledge-section-actions">
                      <button disabled={!selectedGraphNodeSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphNodeSourcePath)} type="button">来源</button>
                      <button disabled={nativeGraphLoadingSlug === selectedGraphNode.id} onClick={() => void handleLoadNativeGraphContext(selectedGraphNode.id)} type="button">
                        {nativeGraphLoadingSlug === selectedGraphNode.id ? "读取..." : isCustomerWorkspace ? "读取支撑信息" : "读取原生上下文"}
                      </button>
                    </div>
                  </div>
                  <article className="workspace-knowledge-node-detail">
                    <div>
                      <strong>{selectedGraphNode.title}</strong>
                      <span>{[selectedGraphNode.entity_type, selectedGraphNode.source_file || selectedGraphNode.file].filter(Boolean).join(" · ")}</span>
                      {selectedGraphNodeSourcePath ? <small>可预览来源：{selectedGraphNodeSourcePath}</small> : <small>citation：{graphCitationString(selectedGraphNode.citation, "file") || selectedGraphNode.file}</small>}
                    </div>
                    {selectedGraphNodeEdges.length ? (
                      <div>
                        <small>关联关系</small>
                        {selectedGraphNodeEdges.map((edge) => {
                          const otherNodeId = edge.from === selectedGraphNode.id ? edge.to : edge.from;
                          return (
                            <button key={edge.id} onClick={() => setSelectedGraphNodeId(otherNodeId)} type="button">
                              {edge.relation_type} · {nodeTitleById.get(otherNodeId) || otherNodeId}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                    {selectedGraphNodeEvents.length ? (
                      <div>
                        <small>关联事件</small>
                        {selectedGraphNodeEvents.map((event) => (
                          <button key={event.id} onClick={() => setSelectedGraphEventId(event.id)} type="button">
                            {[event.date, event.title, event.source_file].filter(Boolean).join(" · ")}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                </section>
              ) : null}
              <section className="workspace-knowledge-graph-section">
                <h3>关系</h3>
                {filteredGraphEdges.slice(0, 10).map((edge) => (
                  <div className="workspace-knowledge-relation-row" key={edge.id}>
                    <button title={edge.from} onClick={() => setSelectedGraphNodeId(edge.from)} type="button">{nodeTitleById.get(edge.from) || edge.from}</button>
                    <small>{edge.relation_type}</small>
                    <button title={edge.to} onClick={() => setSelectedGraphNodeId(edge.to)} type="button">{nodeTitleById.get(edge.to) || edge.to}</button>
                  </div>
                ))}
                {filteredGraphEdges.length === 0 ? <p className="workspace-knowledge-empty">暂无匹配的关系边。</p> : null}
              </section>
              <section className="workspace-knowledge-graph-section">
                <div className="workspace-knowledge-section-header">
                  <h3>Timeline</h3>
                  <div className="workspace-knowledge-timeline-filter" aria-label="Timeline 筛选">
                    {[
                      { key: "all", label: "全部" },
                      { key: "dated", label: "有日期" },
                      { key: "undated", label: "未标日期" },
                      { key: "selected", label: "当前节点" },
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
                  <div className="workspace-knowledge-timeline-tools" aria-label="Timeline 显示控制">
                    <button
                      aria-pressed={graphTimelineDensity === "compact"}
                      className={graphTimelineDensity === "compact" ? "is-active" : ""}
                      onClick={() => setGraphTimelineDensity((value) => (value === "compact" ? "detail" : "compact"))}
                      type="button"
                    >
                      {graphTimelineDensity === "compact" ? "紧凑" : "详细"}
                    </button>
                    <button
                      aria-pressed={graphTimelineDensity === "axis"}
                      className={graphTimelineDensity === "axis" ? "is-active" : ""}
                      onClick={() => setGraphTimelineDensity((value) => (value === "axis" ? "detail" : "axis"))}
                      title="时间轴模式：以可视化时间线排列事件"
                      type="button"
                    >
                      时间轴
                    </button>
                    <button disabled={timelineGroups.length === 0} onClick={() => collapseAllTimelineGroups(timelineGroupLabels)} type="button">
                      折叠
                    </button>
                    <button disabled={collapsedTimelineGroups.size === 0} onClick={expandAllTimelineGroups} type="button">
                      展开
                    </button>
                  </div>
                </div>
                {(graphTimelineDensity === "axis" && timelineGroups.length > 0) ? (
                <div className="workspace-knowledge-timeline-axis" aria-label="Timeline 时间轴">
                  <div className="workspace-knowledge-timeline-axis-line" />
                  {timelineGroups
                    .filter((group) => group.label !== "未标日期")
                    .flatMap((group) => group.events.map((event) => ({ ...event, groupLabel: group.label })))
                    .sort((a, b) => (graphEventTimestamp(a.date) ?? 0) - (graphEventTimestamp(b.date) ?? 0))
                    .slice(0, 30)
                    .map((event, idx, arr) => {
                      const ts = graphEventTimestamp(event.date);
                      const minTs = graphEventTimestamp(arr[0].date) ?? ts ?? Date.now();
                      const maxTs = graphEventTimestamp(arr[arr.length - 1].date) ?? ts ?? Date.now();
                      const range = Math.max(1, (maxTs ?? minTs ?? 0) - (minTs ?? 0));
                      const offset = range > 0 ? ((ts ?? minTs ?? 0) - (minTs ?? 0)) / range : 0.5;
                      const leftPct = Math.max(2, Math.min(98, offset * 100));
                      const isSelected = selectedGraphEventId === event.id;
                      const nodeTitle = nodeTitleById.get(event.entity_id) || "";
                      return (
                        <div
                          className={`workspace-knowledge-timeline-axis-point ${isSelected ? "is-selected" : ""}`}
                          key={event.id}
                          onClick={() => setSelectedGraphEventId(event.id)}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedGraphEventId(event.id); } }}
                          role="button"
                          style={{ left: `${leftPct}%` }}
                          tabIndex={0}
                          title={`${event.date || "无日期"} · ${event.title} · ${nodeTitle}`}
                        >
                          <div className="workspace-knowledge-timeline-axis-dot" />
                          <div className="workspace-knowledge-timeline-axis-label">
                            <span>{event.date}</span>
                            <strong>{graphCanvasLabel(event.title)}</strong>
                            {nodeTitle ? <small>{nodeTitle}</small> : null}
                          </div>
                        </div>
                      );
                    })}
                  {timelineGroups.filter((group) => group.label === "未标日期").length > 0 ? (
                    <div className="workspace-knowledge-timeline-axis-undated">
                      <span>+{timelineGroups.filter((group) => group.label === "未标日期").reduce((sum, g) => sum + g.events.length, 0)} 个未标日期事件</span>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {timelineGroups.map((group) => (
                  <div className={`workspace-knowledge-timeline-group ${collapsedTimelineGroups.has(group.label) ? "is-collapsed" : ""}`} key={group.label}>
                    <div className="workspace-knowledge-timeline-date">
                      <button
                        aria-expanded={!collapsedTimelineGroups.has(group.label)}
                        onClick={() => toggleTimelineGroup(group.label)}
                        type="button"
                      >
                        <span>{group.label}</span>
                        <small>{collapsedTimelineGroups.has(group.label) ? "已折叠" : `${group.events.length} 个事件`}</small>
                      </button>
                    </div>
                    <div className={`workspace-knowledge-timeline-items is-${graphTimelineDensity}`}>
                      {group.events.map((event) => (
                        <button
                          className={`workspace-knowledge-event-row ${selectedGraphEventId === event.id ? "is-selected" : ""} ${graphTimelineDensity === "compact" ? "is-compact" : ""}`}
                          key={event.id}
                          onClick={() => {
                            setSelectedGraphNodeId(event.entity_id);
                            setSelectedGraphEventId(event.id);
                          }}
                          type="button"
                        >
                          <strong>{event.title}</strong>
                          <span>{[event.date, nodeTitleById.get(event.entity_id) || event.entity_id, event.source_file].filter(Boolean).join(" · ")}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                {timelineHiddenCount > 0 ? <p className="workspace-knowledge-empty">当前密度下隐藏 {timelineHiddenCount} 个事件，可切换紧凑显示更多。</p> : null}
                {timelineGroups.length === 0 ? <p className="workspace-knowledge-empty">{knowledgeGraph.warnings?.[0] || "暂无匹配的事件记录。"}</p> : null}
              </section>
              {selectedGraphEvent ? (
                <section className="workspace-knowledge-graph-section">
                  <div className="workspace-knowledge-section-header">
                    <h3>事件详情</h3>
                    <div className="workspace-knowledge-section-actions">
                      <button disabled={!selectedGraphEventSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphEventSourcePath)} type="button">来源</button>
                      <button onClick={() => setSelectedGraphEventId(null)} type="button">清除</button>
                    </div>
                  </div>
                  <article className="workspace-knowledge-event-detail">
                    <strong>{selectedGraphEvent.title}</strong>
                    <span>{[selectedGraphEvent.date || "未标日期", nodeTitleById.get(selectedGraphEvent.entity_id) || selectedGraphEvent.entity_id].filter(Boolean).join(" · ")}</span>
                    {selectedGraphEvent.source_file ? <small>来源：{selectedGraphEvent.source_file}</small> : null}
                    {selectedGraphEventSourcePath ? <small>可预览来源：{selectedGraphEventSourcePath}</small> : null}
                    {selectedGraphEvent.citation ? (
                      <small title={JSON.stringify(selectedGraphEvent.citation)}>citation：{graphCitationString(selectedGraphEvent.citation, "file") || "已绑定"}</small>
                    ) : (
                      <small>暂无 citation。</small>
                    )}
                  </article>
                </section>
              ) : null}
              {(nativeGraphContext || nativeGraphMessage) ? (
                <section className="workspace-knowledge-graph-section">
                  <h3>{isCustomerWorkspace ? "客户情报支撑信息" : "GBrain 原生上下文"}</h3>
                  {nativeGraphMessage ? <p className="workspace-knowledge-empty">{nativeGraphMessage}</p> : null}
                  {nativeGraphContext && nativeCounts ? (
                    <div className="workspace-native-context-card">
                      <strong title={nativeGraphContext.slug}>{nativeGraphContext.slug}</strong>
                      <span>{nativeGraphContext.source_id || knowledgeGraph.source_id}</span>
                      <small>graph {nativeCounts.traverse} · timeline {nativeCounts.timeline} · backlinks {nativeCounts.backlinks}</small>
                    </div>
                  ) : null}
                  {nativeContextSections.map((section) => (
                    <div className="workspace-native-context-section" key={section.key}>
                      <div>
                        <strong>{section.title}</strong>
                        <small>{section.items.length} shown</small>
                      </div>
                      {section.items.length > 0 ? section.items.map((item) => (
                        <article className="workspace-native-context-row" key={item.id}>
                          <strong title={item.title}>{item.title}</strong>
                          <span title={item.subtitle}>{item.subtitle}</span>
                          {item.detail ? <small title={item.detail}>{item.detail}</small> : null}
                        </article>
                      )) : (
                        <p className="workspace-knowledge-empty">暂无 {section.title} 明细。</p>
                      )}
                    </div>
                  ))}
                </section>
              ) : null}
              {canShowEntityMergeReview ? (
                <section className="workspace-knowledge-graph-section">
                  <div className="workspace-knowledge-section-header">
                    <h3>实体候选</h3>
                    <button disabled={entityMergeLoading} onClick={() => void handleLoadEntityMergeCandidates()} type="button">
                      {entityMergeLoading ? "处理中..." : "加载"}
                    </button>
                  </div>
                  {entityMergeMessage ? <p className="workspace-knowledge-empty">{entityMergeMessage}</p> : null}
                  {visibleEntityCandidates.map((candidate) => {
                    const targets = (candidate.target_nodes ?? []).map((node) => node.title).filter(Boolean).join(", ");
                    const evidence = (candidate.evidence_edges ?? []).map((edge) => edge.evidence).filter(Boolean).join(", ");
                    const canCreate = candidate.suggested_action === "create_entity_page" || candidate.suggested_action === "create_event_page";
                    const canRecordAlias = candidate.suggested_action === "merge_duplicate_pages" || candidate.suggested_action === "link_to_existing_entity";
                    return (
                      <article className="workspace-knowledge-candidate-card" key={candidate.id}>
                        <div>
                          <strong>{candidate.title}</strong>
                          <span>{candidate.candidate_type} · {candidate.suggested_action}</span>
                          <small>{targets || evidence || candidate.reason || "需要人工判断"}</small>
                        </div>
                        <div>
                          <button disabled={entityMergeLoading || !canCreate} onClick={() => void handleApplyEntityMergeCandidate(candidate, "create_entity_page")} type="button">建档</button>
                          <button disabled={entityMergeLoading || !canRecordAlias} onClick={() => void handlePreviewEntityMergeCandidate(candidate)} type="button">预览</button>
                          <button disabled={entityMergeLoading || !canRecordAlias} onClick={() => void handleApplyEntityMergeCandidate(candidate, "record_alias")} type="button">别名</button>
                          <button disabled={entityMergeLoading || !canRecordAlias} onClick={() => void handleApplyEntityMergeCandidate(candidate, "apply_relink_changes")} type="button">改写</button>
                          <button disabled={entityMergeLoading} onClick={() => void handleApplyEntityMergeCandidate(candidate, "dismiss")} type="button">忽略</button>
                        </div>
                      </article>
                    );
                  })}
                  {entityMergePreview ? (
                    <article className="workspace-knowledge-merge-preview">
                      <div>
                        <strong>合并预览</strong>
                        <span>{entityMergePreview.planned_alias_review_file || "未生成 alias 文件路径"}</span>
                      </div>
                      <small>
                        主实体：{entityMergePreview.canonical_entity?.title || "-"} · 别名：{(entityMergePreview.alias_entities ?? []).map((node) => node.title).join(", ") || "-"}
                      </small>
                      {(entityMergePreview.planned_relink_changes ?? []).slice(0, 5).map((change) => (
                        <p key={`${change.page_id}-${change.field}-${change.index}`}>
                          <span>{change.page_title}</span>
                          <code>{change.diff_preview}</code>
                        </p>
                      ))}
                      {(entityMergePreview.planned_relink_changes ?? []).length === 0 ? <small>未发现需要自动改写的 frontmatter 引用。</small> : null}
                    </article>
                  ) : null}
                  {entityMergeCandidates && visibleEntityCandidates.length === 0 ? <p className="workspace-knowledge-empty">暂无实体候选。</p> : null}
                </section>
              ) : null}
            </>
          ) : null}
        </div>
      </aside>

  );
}
