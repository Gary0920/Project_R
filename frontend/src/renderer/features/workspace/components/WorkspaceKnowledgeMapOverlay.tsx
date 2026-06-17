import type { MouseEvent, WheelEvent } from "react";

import type { WorkspaceKnowledgeGraphResponse } from "../../../shared/api/types";
import { XmarkIcon } from "../../../shared/icons/LineIcons";
import {
  crmEntityLabel,
  crmRelationLabel,
  graphCanvasLargeLabel,
  graphPreviewSourcePath,
} from "../knowledgeGraphUtils";
import { buildWorkspaceKnowledgeGraphViewModel } from "../workspaceKnowledgeGraphViewModel";

type KnowledgeGraphViewModel = ReturnType<typeof buildWorkspaceKnowledgeGraphViewModel>;

export type WorkspaceKnowledgeMapOverlayProps = {
  graphTimelineFilter: "all" | "dated" | "undated" | "selected";
  handleKnowledgeGraphCanvasPanStart: (event: MouseEvent<HTMLDivElement>) => void;
  handleKnowledgeGraphCanvasWheel: (event: WheelEvent<HTMLDivElement>) => void;
  isCustomerWorkspace: boolean;
  knowledgeGraph: WorkspaceKnowledgeGraphResponse | null;
  knowledgeGraphCanvasOpen: boolean;
  knowledgeGraphCanvasPanning: boolean;
  knowledgeGraphCanvasView: { x: number; y: number; scale: number };
  knowledgeGraphLabel: string;
  openGraphSourcePreview: (sourcePath: string) => void | Promise<void>;
  resetKnowledgeGraphCanvasView: () => void;
  setGraphTimelineFilter: (value: "all" | "dated" | "undated" | "selected") => void;
  setKnowledgeGraphCanvasOpen: (open: boolean) => void;
  setSelectedGraphEventId: (id: string | null) => void;
  setSelectedGraphNodeId: (id: string | null) => void;
  selectedGraphNodeId: string | null;
  viewModel: KnowledgeGraphViewModel;
  workspaceName?: string;
  zoomKnowledgeGraphCanvas: (delta: number) => void;
};

export function WorkspaceKnowledgeMapOverlay({
  handleKnowledgeGraphCanvasPanStart,
  handleKnowledgeGraphCanvasWheel,
  isCustomerWorkspace,
  knowledgeGraph,
  knowledgeGraphCanvasOpen,
  knowledgeGraphCanvasPanning,
  knowledgeGraphCanvasView,
  knowledgeGraphLabel,
  openGraphSourcePreview,
  resetKnowledgeGraphCanvasView,
  setGraphTimelineFilter,
  setKnowledgeGraphCanvasOpen,
  setSelectedGraphEventId,
  setSelectedGraphNodeId,
  selectedGraphNodeId,
  viewModel,
  workspaceName,
  zoomKnowledgeGraphCanvas,
}: WorkspaceKnowledgeMapOverlayProps) {
  if (!knowledgeGraphCanvasOpen || !knowledgeGraph) return null;
  const {
    filteredGraphEvents,
    graphDegreeById,
    largeGraphEdges,
    largeGraphNodes,
    largeGraphPositions,
    nodeTitleById,
    selectedGraphNode,
    selectedGraphNodeEdges,
    selectedGraphNodeEvents,
    selectedGraphNodeSourcePath,
    selectedNeighborIds,
  } = viewModel;

  return (
    <div className="workspace-knowledge-map-overlay" role="dialog" aria-modal="true" aria-label={`${knowledgeGraphLabel}大画布`}>
      <section className="workspace-knowledge-map-shell">
        <header className="workspace-knowledge-map-header">
          <div>
            <span>{knowledgeGraph.source_id || workspaceName || "当前工作区"}</span>
            <strong>{knowledgeGraphLabel}大画布</strong>
          </div>
          <div className="workspace-knowledge-map-header-actions">
            <small>{largeGraphNodes.length} 节点 · {largeGraphEdges.length} 边 · {filteredGraphEvents.length} 事件</small>
            <button aria-label="缩小图谱" onClick={() => zoomKnowledgeGraphCanvas(-0.16)} title="缩小" type="button">-</button>
            <button aria-label="重置图谱视图" onClick={resetKnowledgeGraphCanvasView} title="重置视图" type="button">{Math.round(knowledgeGraphCanvasView.scale * 100)}%</button>
            <button aria-label="放大图谱" onClick={() => zoomKnowledgeGraphCanvas(0.16)} title="放大" type="button">+</button>
            <button aria-label="关闭大画布" onClick={() => setKnowledgeGraphCanvasOpen(false)} title="关闭" type="button"><XmarkIcon /></button>
          </div>
        </header>
        <div className="workspace-knowledge-map-content">
          <div
            className={`workspace-knowledge-map-canvas ${knowledgeGraphCanvasPanning ? "is-panning" : ""}`}
            onMouseDown={handleKnowledgeGraphCanvasPanStart}
            onWheel={handleKnowledgeGraphCanvasWheel}
          >
            <svg viewBox="0 0 960 560" preserveAspectRatio="xMidYMid meet">
              <defs>
                <marker id="workspace-graph-large-arrow" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
                  <path d="M0,0 L7,3 L0,6 Z" />
                </marker>
              </defs>
              <g transform={`translate(${knowledgeGraphCanvasView.x} ${knowledgeGraphCanvasView.y}) scale(${knowledgeGraphCanvasView.scale})`}>
                {largeGraphEdges.map((edge) => {
                  const from = largeGraphPositions.get(edge.from);
                  const to = largeGraphPositions.get(edge.to);
                  if (!from || !to) return null;
                  const isActive = Boolean(selectedGraphNode && (edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id));
                  return (
                    <g className={`workspace-knowledge-map-edge ${isActive ? "is-active" : ""}`} key={edge.id}>
                      <line markerEnd="url(#workspace-graph-large-arrow)" x1={from.x} x2={to.x} y1={from.y} y2={to.y} />
                      <title>{`${nodeTitleById.get(edge.from) || edge.from} -> ${isCustomerWorkspace ? crmRelationLabel(edge.relation_type) : edge.relation_type} -> ${nodeTitleById.get(edge.to) || edge.to}`}</title>
                    </g>
                  );
                })}
                {largeGraphNodes.map((node) => {
                  const point = largeGraphPositions.get(node.id);
                  if (!point) return null;
                  const degree = graphDegreeById.get(node.id) ?? 0;
                  const radius = Math.max(20, Math.min(34, 20 + degree * 2));
                  const isSelected = selectedGraphNodeId === node.id;
                  const isNeighbor = selectedNeighborIds.has(node.id);
                  return (
                    <g
                      className={`workspace-knowledge-map-node ${isSelected ? "is-selected" : ""} ${isNeighbor ? "is-neighbor" : ""}`}
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
                      <circle r={isSelected ? radius + 4 : radius} />
                      <text textAnchor="middle" y="-2">{graphCanvasLargeLabel(node.title)}</text>
                      <text className="workspace-knowledge-map-node-type" textAnchor="middle" y="13">{isCustomerWorkspace ? crmEntityLabel(node.entity_type) : node.entity_type || "entity"}</text>
                      <title>{`${node.title} · ${isCustomerWorkspace ? crmEntityLabel(node.entity_type) : node.entity_type || "entity"} · ${degree} 条关系`}</title>
                    </g>
                  );
                })}
              </g>
            </svg>
            <div className="workspace-knowledge-map-legend">
              <span>滚轮缩放，拖动画布空白处平移</span>
              <span>点击节点后，右侧详情与侧栏详情同步</span>
            </div>
          </div>
          <aside className="workspace-knowledge-map-inspector">
            {selectedGraphNode ? (
              <>
                <section>
                  <small>当前节点</small>
                  <strong>{selectedGraphNode.title}</strong>
                  <span>{[isCustomerWorkspace ? crmEntityLabel(selectedGraphNode.entity_type) : selectedGraphNode.entity_type, selectedGraphNode.source_file || selectedGraphNode.file].filter(Boolean).join(" · ") || "未标来源"}</span>
                  <button disabled={!selectedGraphNodeSourcePath} onClick={() => void openGraphSourcePreview(selectedGraphNodeSourcePath)} type="button">
                    <span>Source preview</span>
                    <strong>{selectedGraphNodeSourcePath || "无可预览来源"}</strong>
                  </button>
                </section>
                <section>
                  <small>关联关系</small>
                  {selectedGraphNodeEdges.length ? selectedGraphNodeEdges.map((edge) => {
                    const otherNodeId = edge.from === selectedGraphNode.id ? edge.to : edge.from;
                    return (
                      <button key={edge.id} onClick={() => setSelectedGraphNodeId(otherNodeId)} type="button">
                        <span>{isCustomerWorkspace ? crmRelationLabel(edge.relation_type) : edge.relation_type}</span>
                        <strong>{nodeTitleById.get(otherNodeId) || otherNodeId}</strong>
                      </button>
                    );
                  }) : <p>当前筛选下暂无关系。</p>}
                </section>
                <section>
                  <small>相关事件</small>
                  {selectedGraphNodeEvents.length ? selectedGraphNodeEvents.map((event) => (
                    <div className="workspace-knowledge-map-event-card" key={event.id}>
                      <button onClick={() => { setSelectedGraphEventId(event.id); setGraphTimelineFilter("selected"); }} type="button">
                        <span>{event.date || "未标日期"}</span>
                        <strong>{event.title}</strong>
                      </button>
                      <button disabled={!graphPreviewSourcePath(event)} onClick={() => void openGraphSourcePreview(graphPreviewSourcePath(event))} type="button">
                        <span>来源</span>
                        <strong>{graphPreviewSourcePath(event) || "无可预览来源"}</strong>
                      </button>
                    </div>
                  )) : <p>暂无事件。</p>}
                </section>
              </>
            ) : (
              <section>
                <small>未选择节点</small>
                <p>点击画布中的实体节点查看关系和事件。</p>
              </section>
            )}
          </aside>
        </div>
      </section>
    </div>
  );
}
