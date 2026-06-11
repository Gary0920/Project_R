import type {
  WorkspaceEntityMergeCandidatesResponse,
  WorkspaceKnowledgeGraphResponse,
  WorkspaceNativeGraphContextResponse,
} from "../../shared/api/types";
import {
  crmEntityLabel,
  graphEventGroupLabel,
  graphEventTimestamp,
  graphForceLayout,
  graphPreviewSourcePath,
  nativeResultCount,
  nativeResultItems,
} from "./knowledgeGraphUtils";

export type GraphTimelineFilter = "all" | "dated" | "undated" | "selected";
export type GraphTimelineDensity = "detail" | "compact" | "axis";

type ProfileCard = WorkspaceKnowledgeGraphResponse["profile_cards"][number];

export function buildWorkspaceKnowledgeGraphViewModel({
  knowledgeGraph,
  nativeGraphContext,
  entityMergeCandidates,
  graphSearchTerm,
  graphEntityFilter,
  selectedGraphNodeId,
  selectedGraphEventId,
  graphTimelineFilter,
  graphTimelineDensity,
  isCustomerWorkspace,
}: {
  knowledgeGraph: WorkspaceKnowledgeGraphResponse | null;
  nativeGraphContext: WorkspaceNativeGraphContextResponse | null;
  entityMergeCandidates: WorkspaceEntityMergeCandidatesResponse | null;
  graphSearchTerm: string;
  graphEntityFilter: string;
  selectedGraphNodeId: string | null;
  selectedGraphEventId: string | null;
  graphTimelineFilter: GraphTimelineFilter;
  graphTimelineDensity: GraphTimelineDensity;
  isCustomerWorkspace: boolean;
}) {
  const nodeTitleById = new Map((knowledgeGraph?.nodes ?? []).map((node) => [node.id, node.title]));
  const graphNodeById = new Map((knowledgeGraph?.nodes ?? []).map((node) => [node.id, node]));
  const graphSearch = graphSearchTerm.trim().toLowerCase();
  const graphEntityTypes = Array.from(
    new Set((knowledgeGraph?.nodes ?? []).map((node) => node.entity_type).filter((item): item is string => Boolean(item))),
  ).sort((a, b) => a.localeCompare(b));
  const graphNodeMatches = (nodeId: string) => {
    const node = graphNodeById.get(nodeId);
    if (!node) return false;
    if (graphEntityFilter !== "all" && node.entity_type !== graphEntityFilter) return false;
    if (!graphSearch) return true;
    return [node.title, node.entity_type, node.file, node.source_file]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(graphSearch);
  };
  const filteredGraphNodes = (knowledgeGraph?.nodes ?? []).filter((node) => graphNodeMatches(node.id));
  const filteredGraphNodeIds = new Set(filteredGraphNodes.map((node) => node.id));
  const filteredProfileCards = (knowledgeGraph?.profile_cards ?? []).filter((card) => filteredGraphNodeIds.has(card.id));
  const filteredGraphEdges = (knowledgeGraph?.edges ?? []).filter((edge) => {
    const from = graphNodeById.get(edge.from);
    const to = graphNodeById.get(edge.to);
    const typeMatches = graphEntityFilter === "all" || from?.entity_type === graphEntityFilter || to?.entity_type === graphEntityFilter;
    const searchMatches = !graphSearch || [from?.title, to?.title, edge.relation_type, edge.evidence, edge.source_field]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(graphSearch);
    return typeMatches && searchMatches;
  });
  const filteredGraphEvents = (knowledgeGraph?.events ?? []).filter((event) => {
    const node = graphNodeById.get(event.entity_id);
    const typeMatches = graphEntityFilter === "all" || node?.entity_type === graphEntityFilter;
    const searchMatches = !graphSearch || [event.title, event.date, event.source_file, node?.title]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(graphSearch);
    return typeMatches && searchMatches;
  });
  const selectedGraphNode = selectedGraphNodeId ? graphNodeById.get(selectedGraphNodeId) ?? null : null;
  const selectedGraphNodeEdges = selectedGraphNode
    ? (knowledgeGraph?.edges ?? []).filter((edge) => edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id).slice(0, 8)
    : [];
  const selectedGraphNodeEvents = selectedGraphNode
    ? (knowledgeGraph?.events ?? []).filter((event) => event.entity_id === selectedGraphNode.id).slice(0, 6)
    : [];
  const selectedGraphEvent = selectedGraphEventId
    ? (knowledgeGraph?.events ?? []).find((event) => event.id === selectedGraphEventId) ?? null
    : null;
  const selectedGraphNodeSourcePath = graphPreviewSourcePath(selectedGraphNode);
  const selectedGraphEventSourcePath = graphPreviewSourcePath(selectedGraphEvent);
  const timelineEvents = filteredGraphEvents
    .filter((event) => {
      if (graphTimelineFilter === "dated") return Boolean(event.date);
      if (graphTimelineFilter === "undated") return !event.date;
      if (graphTimelineFilter === "selected") return Boolean(selectedGraphNode && event.entity_id === selectedGraphNode.id);
      return true;
    })
    .slice()
    .sort((a, b) => {
      const left = graphEventTimestamp(a.date) ?? -Infinity;
      const right = graphEventTimestamp(b.date) ?? -Infinity;
      return right - left;
    });
  const timelineVisibleLimit = graphTimelineDensity === "compact" ? 48 : 24;
  const timelineVisibleEvents = timelineEvents.slice(0, timelineVisibleLimit);
  const timelineHiddenCount = Math.max(0, timelineEvents.length - timelineVisibleEvents.length);
  const timelineGroups = timelineVisibleEvents.reduce<Array<{ label: string; events: typeof timelineVisibleEvents }>>((groups, event) => {
    const label = graphEventGroupLabel(event.date);
    const existing = groups.find((group) => group.label === label);
    if (existing) {
      existing.events.push(event);
      return groups;
    }
    groups.push({ label, events: [event] });
    return groups;
  }, []);
  const timelineGroupLabels = timelineGroups.map((group) => group.label);
  const graphDegreeById = new Map<string, number>();
  for (const edge of filteredGraphEdges) {
    graphDegreeById.set(edge.from, (graphDegreeById.get(edge.from) ?? 0) + 1);
    graphDegreeById.set(edge.to, (graphDegreeById.get(edge.to) ?? 0) + 1);
  }
  const selectedNeighborIds = new Set(
    selectedGraphNode
      ? (knowledgeGraph?.edges ?? [])
        .filter((edge) => edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id)
        .map((edge) => edge.from === selectedGraphNode.id ? edge.to : edge.from)
      : [],
  );
  const sortedGraphNodes = filteredGraphNodes
    .slice()
    .sort((left, right) => (graphDegreeById.get(right.id) ?? 0) - (graphDegreeById.get(left.id) ?? 0) || left.title.localeCompare(right.title));
  const canvasGraphNodes = selectedGraphNode
    ? [
      selectedGraphNode,
      ...sortedGraphNodes.filter((node) => node.id !== selectedGraphNode.id && selectedNeighborIds.has(node.id)),
      ...sortedGraphNodes.filter((node) => node.id !== selectedGraphNode.id && !selectedNeighborIds.has(node.id)),
    ].slice(0, 12)
    : sortedGraphNodes.slice(0, 12);
  const canvasGraphNodeIds = new Set(canvasGraphNodes.map((node) => node.id));
  const canvasGraphForceNodes = canvasGraphNodes.map((node) => ({
    id: node.id,
    degree: graphDegreeById.get(node.id) ?? 0,
    isFocus: Boolean(selectedGraphNode && node.id === selectedGraphNode.id),
    isNeighbor: selectedNeighborIds.has(node.id),
    entityType: node.entity_type ?? "page",
  }));
  const canvasGraphEdges = filteredGraphEdges.filter((edge) => canvasGraphNodeIds.has(edge.from) && canvasGraphNodeIds.has(edge.to)).slice(0, 24);
  const canvasGraphPositions = graphForceLayout(
    canvasGraphForceNodes,
    canvasGraphEdges,
    340, 216, 72,
  );
  const largeGraphNodes = selectedGraphNode
    ? [
      selectedGraphNode,
      ...sortedGraphNodes.filter((node) => node.id !== selectedGraphNode.id && selectedNeighborIds.has(node.id)),
      ...sortedGraphNodes.filter((node) => node.id !== selectedGraphNode.id && !selectedNeighborIds.has(node.id)),
    ].slice(0, 40)
    : sortedGraphNodes.slice(0, 40);
  const largeGraphNodeIds = new Set(largeGraphNodes.map((node) => node.id));
  const largeGraphEdges = filteredGraphEdges.filter((edge) => largeGraphNodeIds.has(edge.from) && largeGraphNodeIds.has(edge.to)).slice(0, 80);
  const largeGraphForceNodes = largeGraphNodes.map((node) => ({
    id: node.id,
    degree: graphDegreeById.get(node.id) ?? 0,
    isFocus: Boolean(selectedGraphNode && node.id === selectedGraphNode.id),
    isNeighbor: selectedNeighborIds.has(node.id),
    entityType: node.entity_type ?? "page",
  }));
  const largeGraphPositions = graphForceLayout(
    largeGraphForceNodes,
    largeGraphEdges,
    960, 560, 210,
  );
  const visibleEntityCandidates = (entityMergeCandidates?.candidates ?? []).slice(0, 8);
  const nativeCounts = nativeGraphContext ? {
    traverse: nativeResultCount(nativeGraphContext.traverse_graph),
    timeline: nativeResultCount(nativeGraphContext.timeline),
    backlinks: nativeResultCount(nativeGraphContext.backlinks),
  } : null;
  const nativeContextSections = nativeGraphContext ? [
    { key: "graph", title: isCustomerWorkspace ? "关系路径" : "Graph traversal", items: nativeResultItems(nativeGraphContext.traverse_graph, "graph") },
    { key: "timeline", title: isCustomerWorkspace ? "互动时间线" : "Timeline", items: nativeResultItems(nativeGraphContext.timeline, "timeline") },
    { key: "backlinks", title: isCustomerWorkspace ? "相关来源" : "Backlinks", items: nativeResultItems(nativeGraphContext.backlinks, "backlinks") },
  ] : [];
  const crmRecentEvents = timelineEvents.slice(0, 12);
  const crmPersonCount = filteredGraphNodes.filter((node) => crmEntityLabel(node.entity_type) === "联系人").length;
  const crmCompanyCount = filteredGraphNodes.filter((node) => crmEntityLabel(node.entity_type) === "公司").length;
  const crmProjectCount = filteredGraphNodes.filter((node) => crmEntityLabel(node.entity_type) === "项目").length;
  const crmDatedEventCount = filteredGraphEvents.filter((event) => Boolean(event.date)).length;
  const crmCardRole = (card: { entity_type: string }) => crmEntityLabel(card.entity_type);
  const crmSortedProfileCards = filteredProfileCards
    .slice()
    .sort((left, right) => (
      (right.event_count - left.event_count)
      || (right.relation_count - left.relation_count)
      || left.title.localeCompare(right.title)
    ));
  const crmMostActiveContact = crmSortedProfileCards.find((card) => crmCardRole(card) === "联系人" && card.event_count > 0)
    ?? crmSortedProfileCards.find((card) => crmCardRole(card) === "联系人")
    ?? null;
  const crmRelationshipHub = crmSortedProfileCards
    .slice()
    .sort((left, right) => (right.relation_count - left.relation_count) || (right.event_count - left.event_count))
    .find((card) => card.relation_count > 0)
    ?? null;
  const crmLatestEvent = crmRecentEvents[0] ?? null;
  const crmVisibleProfileCards = [
    ...crmSortedProfileCards.filter((card) => crmCardRole(card) === "联系人").slice(0, 5),
    ...crmSortedProfileCards.filter((card) => crmCardRole(card) === "公司").slice(0, 4),
    ...crmSortedProfileCards.filter((card) => crmCardRole(card) === "项目").slice(0, 4),
    ...crmSortedProfileCards.filter((card) => !["联系人", "公司", "项目"].includes(crmCardRole(card))).slice(0, 3),
  ].filter((card, index, list) => list.findIndex((item) => item.id === card.id) === index).slice(0, 14);
  const crmCardReason = (card: Pick<ProfileCard, "relation_count" | "event_count">) => {
    if (card.event_count > 0) return `${card.event_count} 次互动，适合先查看沟通脉络`;
    if (card.relation_count >= 12) return `${card.relation_count} 条关系，是关系网中的枢纽`;
    if (card.relation_count > 0) return `${card.relation_count} 条关系，可查看上下游关联`;
    return "已识别对象，等待更多互动记录";
  };
  const crmSelectedRelations = selectedGraphNode
    ? (knowledgeGraph?.edges ?? [])
      .filter((edge) => edge.from === selectedGraphNode.id || edge.to === selectedGraphNode.id)
      .slice(0, 12)
    : [];
  const crmSelectedEvents = selectedGraphNode
    ? (knowledgeGraph?.events ?? []).filter((event) => event.entity_id === selectedGraphNode.id).slice(0, 8)
    : [];
  const crmCanvasNodes = selectedGraphNode
    ? [
      selectedGraphNode,
      ...sortedGraphNodes.filter((node) => node.id !== selectedGraphNode.id && selectedNeighborIds.has(node.id)),
      ...sortedGraphNodes.filter((node) => node.id !== selectedGraphNode.id && !selectedNeighborIds.has(node.id)),
    ].slice(0, 28)
    : sortedGraphNodes.slice(0, 28);
  const crmCanvasNodeIds = new Set(crmCanvasNodes.map((node) => node.id));
  const crmCanvasEdges = filteredGraphEdges.filter((edge) => crmCanvasNodeIds.has(edge.from) && crmCanvasNodeIds.has(edge.to)).slice(0, 72);
  const crmCanvasPositions = graphForceLayout(
    crmCanvasNodes.map((node) => ({
      id: node.id,
      degree: graphDegreeById.get(node.id) ?? 0,
      isFocus: Boolean(selectedGraphNode && node.id === selectedGraphNode.id),
      isNeighbor: selectedNeighborIds.has(node.id),
      entityType: node.entity_type ?? "page",
    })),
    crmCanvasEdges,
    720,
    420,
    155,
  );

  return {
    nodeTitleById,
    graphNodeById,
    graphEntityTypes,
    filteredGraphNodes,
    filteredProfileCards,
    filteredGraphEdges,
    filteredGraphEvents,
    selectedGraphNode,
    selectedGraphNodeEdges,
    selectedGraphNodeEvents,
    selectedGraphEvent,
    selectedGraphNodeSourcePath,
    selectedGraphEventSourcePath,
    timelineEvents,
    timelineVisibleLimit,
    timelineVisibleEvents,
    timelineHiddenCount,
    timelineGroups,
    timelineGroupLabels,
    graphDegreeById,
    selectedNeighborIds,
    sortedGraphNodes,
    canvasGraphNodes,
    canvasGraphEdges,
    canvasGraphPositions,
    largeGraphNodes,
    largeGraphEdges,
    largeGraphPositions,
    visibleEntityCandidates,
    nativeCounts,
    nativeContextSections,
    crmRecentEvents,
    crmPersonCount,
    crmCompanyCount,
    crmProjectCount,
    crmDatedEventCount,
    crmSortedProfileCards,
    crmMostActiveContact,
    crmRelationshipHub,
    crmLatestEvent,
    crmVisibleProfileCards,
    crmCardReason,
    crmSelectedRelations,
    crmSelectedEvents,
    crmCanvasNodes,
    crmCanvasEdges,
    crmCanvasPositions,
  };
}
