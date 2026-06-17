import { useEffect, useState } from "react";

import {
  applyWorkspaceEntityMergeCandidateAction,
  getWorkspaceEntityMergeCandidatePreview,
  getWorkspaceEntityMergeCandidates,
  getWorkspaceKnowledgeGraph,
  getWorkspaceNativeGraphContext,
} from "../api";
import { normalizeGraphSourcePath } from "../knowledgeGraphUtils";
import {
  buildWorkspaceKnowledgeGraphViewModel,
  type GraphTimelineDensity,
  type GraphTimelineFilter,
} from "../workspaceKnowledgeGraphViewModel";
import type { ApiClientOptions } from "../../../shared/api/client";
import type {
  GBrainEntityMergeCandidate,
  GBrainEntityMergePreviewResponse,
  WorkspaceEntityMergeCandidatesResponse,
  WorkspaceFileItemResponse,
  WorkspaceKnowledgeGraphResponse,
  WorkspaceNativeGraphContextResponse,
} from "../../../shared/api/types";

export function useWorkspaceKnowledgeGraph({
  apiOptions,
  canIngestKnowledge,
  closeFilePreview,
  isCustomerWorkspace,
  onCustomerIntelligenceClose,
  openFilePreview,
  standaloneCustomerIntelligence,
  workspaceId,
  workspaceKind,
}: {
  apiOptions: ApiClientOptions;
  canIngestKnowledge: boolean;
  closeFilePreview: () => void;
  isCustomerWorkspace: boolean;
  onCustomerIntelligenceClose?: () => void;
  openFilePreview: (item: WorkspaceFileItemResponse) => Promise<void>;
  standaloneCustomerIntelligence: boolean;
  workspaceId: number | null;
  workspaceKind: "user" | "project" | "customer";
}) {
  const [knowledgeGraph, setKnowledgeGraph] = useState<WorkspaceKnowledgeGraphResponse | null>(null);
  const [knowledgeGraphOpen, setKnowledgeGraphOpen] = useState(false);
  const [knowledgeGraphCanvasOpen, setKnowledgeGraphCanvasOpen] = useState(false);
  const [knowledgeGraphLoading, setKnowledgeGraphLoading] = useState(false);
  const [knowledgeGraphError, setKnowledgeGraphError] = useState<string | null>(null);
  const [graphSearchTerm, setGraphSearchTerm] = useState("");
  const [graphEntityFilter, setGraphEntityFilter] = useState("all");
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [selectedGraphEventId, setSelectedGraphEventId] = useState<string | null>(null);
  const [graphTimelineFilter, setGraphTimelineFilter] = useState<GraphTimelineFilter>("all");
  const [graphTimelineDensity, setGraphTimelineDensity] = useState<GraphTimelineDensity>("detail");
  const [collapsedTimelineGroups, setCollapsedTimelineGroups] = useState<Set<string>>(() => new Set());
  const [entityMergeCandidates, setEntityMergeCandidates] = useState<WorkspaceEntityMergeCandidatesResponse | null>(null);
  const [entityMergePreview, setEntityMergePreview] = useState<GBrainEntityMergePreviewResponse | null>(null);
  const [entityMergeLoading, setEntityMergeLoading] = useState(false);
  const [entityMergeMessage, setEntityMergeMessage] = useState<string | null>(null);
  const [nativeGraphContext, setNativeGraphContext] = useState<WorkspaceNativeGraphContextResponse | null>(null);
  const [nativeGraphLoadingSlug, setNativeGraphLoadingSlug] = useState<string | null>(null);
  const [nativeGraphMessage, setNativeGraphMessage] = useState<string | null>(null);

  const canShowKnowledgeGraph = workspaceKind === "project" || workspaceKind === "customer";
  const canShowEntityMergeReview = canShowKnowledgeGraph && canIngestKnowledge;
  const knowledgeGraphLabel = isCustomerWorkspace ? "客户情报" : "事件图谱";
  const viewModel = buildWorkspaceKnowledgeGraphViewModel({
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
  });

  async function openGraphSourcePreview(sourcePath: string) {
    const normalized = normalizeGraphSourcePath(sourcePath);
    if (!normalized) {
      setNativeGraphMessage("该 citation 未指向可直接预览的工作区源文件。");
      return;
    }
    const name = normalized.split("/").filter(Boolean).pop() || normalized;
    setKnowledgeGraphOpen(false);
    setKnowledgeGraphCanvasOpen(false);
    await openFilePreview({
      id: null,
      name,
      path: normalized,
      type: "file",
      size: null,
      updated_at: null,
      uploaded_by: null,
      uploader_name: null,
      deleted_at: null,
      deleted_by: null,
      rag_status: null,
      can_delete: false,
      can_restore: false,
      children: [],
    });
  }

  async function handleOpenKnowledgeGraph() {
    if (!workspaceId) return;
    closeFilePreview();
    setKnowledgeGraphOpen(true);
    setKnowledgeGraphLoading(true);
    setKnowledgeGraphError(null);
    try {
      const result = await getWorkspaceKnowledgeGraph(apiOptions, workspaceId, { limit: 120 });
      setKnowledgeGraph(result);
      setSelectedGraphNodeId((current) => {
        if (current && result.nodes.some((node) => node.id === current)) return current;
        return result.profile_cards[0]?.id || result.nodes[0]?.id || null;
      });
      setSelectedGraphEventId((current) => {
        if (current && result.events.some((event) => event.id === current)) return current;
        return null;
      });
    } catch (graphError: unknown) {
      setKnowledgeGraphError(graphError instanceof Error ? graphError.message : "无法加载工作区图谱");
    } finally {
      setKnowledgeGraphLoading(false);
    }
  }

  async function handleLoadEntityMergeCandidates() {
    if (!workspaceId) return;
    setEntityMergeLoading(true);
    setEntityMergeMessage(null);
    try {
      const result = await getWorkspaceEntityMergeCandidates(apiOptions, workspaceId, { limit: 80 });
      setEntityMergeCandidates(result);
      const warning = result.warnings?.find((item) => item.trim());
      setEntityMergeMessage(result.ok ? "实体候选已加载。" : warning || "实体候选加载失败。");
    } catch (candidateError: unknown) {
      setEntityMergeMessage(candidateError instanceof Error ? candidateError.message : "实体候选加载失败");
    } finally {
      setEntityMergeLoading(false);
    }
  }

  async function handleApplyEntityMergeCandidate(candidate: GBrainEntityMergeCandidate, action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes") {
    if (!workspaceId) return;
    setEntityMergeLoading(true);
    setEntityMergeMessage(
      action === "dismiss"
        ? "正在忽略实体候选..."
        : action === "record_alias"
          ? "正在记录实体别名..."
          : action === "apply_relink_changes"
            ? "正在应用引用改写..."
            : "正在创建实体占位页...",
    );
    try {
      const result = await applyWorkspaceEntityMergeCandidateAction(apiOptions, workspaceId, {
        candidate_id: candidate.id,
        action,
      });
      const syncStatus = result.sync?.status ? `，sync=${result.sync.status}` : "";
      setEntityMergeMessage(result.ok ? `实体候选已处理：${result.status}${result.created_file ? `，${result.created_file}` : ""}${syncStatus}。` : result.error || "实体候选处理失败。");
      const refreshed = await getWorkspaceEntityMergeCandidates(apiOptions, workspaceId, { limit: 80 });
      setEntityMergeCandidates(refreshed);
      const graph = await getWorkspaceKnowledgeGraph(apiOptions, workspaceId, { limit: 120 });
      setKnowledgeGraph(graph);
    } catch (candidateError: unknown) {
      setEntityMergeMessage(candidateError instanceof Error ? candidateError.message : "实体候选处理失败");
    } finally {
      setEntityMergeLoading(false);
    }
  }

  async function handlePreviewEntityMergeCandidate(candidate: GBrainEntityMergeCandidate) {
    if (!workspaceId) return;
    setEntityMergeLoading(true);
    setEntityMergeMessage("正在生成实体合并预览...");
    try {
      const result = await getWorkspaceEntityMergeCandidatePreview(apiOptions, workspaceId, candidate.id);
      setEntityMergePreview(result);
      setEntityMergeMessage(`预览已生成：${result.stats?.planned_relink_changes ?? 0} 条引用建议。`);
    } catch (candidateError: unknown) {
      setEntityMergeMessage(candidateError instanceof Error ? candidateError.message : "实体合并预览失败");
    } finally {
      setEntityMergeLoading(false);
    }
  }

  async function handleLoadNativeGraphContext(slug: string) {
    if (!workspaceId || !slug) return;
    setNativeGraphLoadingSlug(slug);
    setNativeGraphMessage(null);
    try {
      const result = await getWorkspaceNativeGraphContext(apiOptions, workspaceId, {
        slug,
        depth: 2,
        direction: "both",
      });
      setSelectedGraphNodeId(slug);
      setNativeGraphContext(result);
      setNativeGraphMessage(result.status === "ok" ? (isCustomerWorkspace ? "客户情报支撑信息已加载。" : "GBrain 原生图谱上下文已加载。") : result.error || (isCustomerWorkspace ? "客户情报支撑信息加载失败。" : "GBrain 原生图谱上下文加载失败。"));
    } catch (nativeError: unknown) {
      setNativeGraphMessage(nativeError instanceof Error ? nativeError.message : (isCustomerWorkspace ? "客户情报支撑信息加载失败" : "GBrain 原生图谱上下文加载失败"));
    } finally {
      setNativeGraphLoadingSlug(null);
    }
  }

  function closeKnowledgeGraph() {
    setKnowledgeGraphOpen(false);
    setKnowledgeGraphCanvasOpen(false);
    onCustomerIntelligenceClose?.();
  }

  function toggleTimelineGroup(label: string) {
    setCollapsedTimelineGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  }

  function collapseAllTimelineGroups(labels: string[]) {
    setCollapsedTimelineGroups(new Set(labels));
  }

  function expandAllTimelineGroups() {
    setCollapsedTimelineGroups(new Set());
  }

  function closeGraphForFilePreview() {
    setKnowledgeGraphOpen(false);
    setKnowledgeGraphCanvasOpen(false);
  }

  useEffect(() => {
    if (!standaloneCustomerIntelligence || workspaceKind !== "customer" || !workspaceId) return;
    void handleOpenKnowledgeGraph();
  }, [standaloneCustomerIntelligence, workspaceKind, workspaceId]);

  return {
    canShowEntityMergeReview,
    canShowKnowledgeGraph,
    closeGraphForFilePreview,
    closeKnowledgeGraph,
    collapsedTimelineGroups,
    collapseAllTimelineGroups,
    entityMergeCandidates,
    entityMergeLoading,
    entityMergeMessage,
    entityMergePreview,
    expandAllTimelineGroups,
    graphEntityFilter,
    graphSearchTerm,
    graphTimelineDensity,
    graphTimelineFilter,
    handleApplyEntityMergeCandidate,
    handleLoadEntityMergeCandidates,
    handleLoadNativeGraphContext,
    handleOpenKnowledgeGraph,
    handlePreviewEntityMergeCandidate,
    knowledgeGraph,
    knowledgeGraphCanvasOpen,
    knowledgeGraphError,
    knowledgeGraphLabel,
    knowledgeGraphLoading,
    knowledgeGraphOpen,
    nativeGraphContext,
    nativeGraphLoadingSlug,
    nativeGraphMessage,
    openGraphSourcePreview,
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
    toggleTimelineGroup,
    viewModel,
  };
}
