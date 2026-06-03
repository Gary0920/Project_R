import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent, type WheelEvent } from "react";

import {
  clearWorkspaceTrash,
  applyWorkspaceEntityMergeCandidateAction,
  copyWorkspacePath,
  createWorkspaceFolder,
  deleteWorkspaceFile,
  deleteWorkspaceFolder,
  enqueueWorkspaceKnowledgeIngest,
  fetchWorkspaceFileBlob,
  getWorkspaceEntityMergeCandidates,
  getWorkspaceEntityMergeCandidatePreview,
  getWorkspaceKnowledgeGraph,
  getWorkspaceKnowledgeIngestJob,
  getWorkspaceNativeGraphContext,
  permanentlyDeleteWorkspaceFile,
  moveWorkspacePath,
  renameWorkspacePath,
  restoreWorkspaceFile,
  listWorkspaceFiles,
  uploadWorkspaceFiles,
} from "../api/workspaces";
import type { ApiClientOptions } from "../api/client";
import type { AgentRunResponse, GBrainEntityMergeCandidate, GBrainEntityMergePreviewResponse, WorkspaceEntityMergeCandidatesResponse, WorkspaceFileItemResponse, WorkspaceKnowledgeGraphResponse, WorkspaceNativeGraphContextResponse } from "../api/types";
import { parseApiDate } from "../utils/time";
import {
  AgentIcon,
  ArrowUpIcon,
  BrainIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  EditIcon,
  MoreIcon,
  MoveIcon,
  MaximizeIcon,
  NoteIcon,
  PlusIcon,
  RefreshIcon,
  TrashIcon,
  WorkspaceIcon,
  XmarkIcon,
} from "./LineIcons";

export type WorkspaceFilePanelProps = {
  apiOptions: ApiClientOptions;
  workspaceId: number | null;
  workspaceName?: string;
  workspaceKind?: string;
  canIngestKnowledge?: boolean;
  defaultPath?: string;
  onReferenceFile?: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  onPreviewOpen?: () => void;
};

type WorkspaceConfirmation = {
  title: string;
  detail: string;
  confirmLabel: string;
  tone: "warning" | "danger";
  onConfirm: () => Promise<void>;
};

type WorkspaceFilePreview = {
  item: WorkspaceFileItemResponse;
  kind: ReturnType<typeof getFileKind>;
  status: "loading" | "ready" | "failed";
  objectUrl?: string;
  text?: string;
  error?: string;
};

type WorkspaceFileContextMenu = {
  item: WorkspaceFileItemResponse;
  x: number;
  y: number;
};

type WorkspaceClipboardItem = {
  action: "copy" | "cut";
  item: WorkspaceFileItemResponse;
};

const TRASH_DIRECTORY = ".trash";
const SYSTEM_WORKSPACE_DIRECTORIES = new Set([".git", "derived", "manifests", ".pending_review"]);
const PROTECTED_WORKSPACE_ROOT_DIRECTORIES = new Set([
  "01-合同与报价",
  "02-图纸与技术资料",
  "03-会议纪要",
  "04-变更与签证",
  "05-生产与发货",
  "06-现场与客诉",
  "01-客户档案",
  "02-联系人与关系",
  "03-沟通记录",
  "04-原始资料",
  "99-未归档文件",
]);
const WORKSPACE_DRAG_MIME = "application/x-project-r-workspace-file";
const PREVIEW_WIDTH_KEY = "project-r:workspace-file-preview-width";
const PREVIEW_MIN_WIDTH = 240;
const PREVIEW_DEFAULT_WIDTH = 320;
const PREVIEW_MAX_WIDTH = 520;
const FILE_LIST_MIN_WIDTH = 300;
const FILE_PANEL_GAP = 10;

function getPreviewMaxWidth(containerWidth?: number) {
  if (!Number.isFinite(containerWidth)) return PREVIEW_MAX_WIDTH;
  return Math.max(PREVIEW_MIN_WIDTH, Math.min(PREVIEW_MAX_WIDTH, Math.round((containerWidth ?? 0) - FILE_LIST_MIN_WIDTH - FILE_PANEL_GAP)));
}

function clampPreviewWidth(value: number, containerWidth?: number) {
  return Math.min(getPreviewMaxWidth(containerWidth), Math.max(PREVIEW_MIN_WIDTH, Math.round(value)));
}

function readPreviewWidth() {
  try {
    const stored = Number(localStorage.getItem(PREVIEW_WIDTH_KEY));
    return Number.isFinite(stored) ? clampPreviewWidth(stored) : PREVIEW_DEFAULT_WIDTH;
  } catch {
    return PREVIEW_DEFAULT_WIDTH;
  }
}

function writePreviewWidth(width: number) {
  try {
    localStorage.setItem(PREVIEW_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

function formatSize(size: number | null) {
  if (size === null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function getRagStatusMeta(status: string | null | undefined) {
  if (status === "indexed") return { label: "已入库", tone: "indexed", title: "已同步到当前工作区知识库" };
  if (status === "failed") return { label: "索引失败", tone: "failed", title: "索引失败，右键文件后可重新处理或联系管理员" };
  if (status === "pending" || status === "pending_review") return { label: "处理中", tone: "processing", title: "正在排队或等待处理" };
  if (status === "pending_extractor_capability") return { label: "待能力", tone: "processing", title: "当前文件类型等待提炼能力补齐" };
  if (status === "pending_transcription") return { label: "待转写", tone: "processing", title: "音视频文件等待转写处理" };
  if (status === "skipped") return { label: "暂不入库", tone: "muted", title: "当前文件暂不进入知识库" };
  return { label: "未入库", tone: "empty", title: "尚未录入当前工作区知识库" };
}

function knowledgeStoreLabel(workspaceKind: string) {
  if (workspaceKind === "customer") return "客户情报库";
  if (workspaceKind === "project") return "项目知识库";
  return "工作区知识库";
}

function isSystemWorkspaceItem(item: WorkspaceFileItemResponse) {
  if (item.type !== "directory") return false;
  return item.path.split("/").some((part) => SYSTEM_WORKSPACE_DIRECTORIES.has(part));
}

function filterSystemWorkspaceItems(items: WorkspaceFileItemResponse[]): WorkspaceFileItemResponse[] {
  return items
    .filter((item) => !isSystemWorkspaceItem(item))
    .map((item) => item.type === "directory" ? { ...item, children: filterSystemWorkspaceItems(item.children ?? []) } : item);
}

function isProtectedWorkspaceDirectory(item: WorkspaceFileItemResponse, workspaceKind: string) {
  return item.type === "directory" && !item.path.includes("/") && (
    item.path === TRASH_DIRECTORY || (workspaceKind !== "user" && PROTECTED_WORKSPACE_ROOT_DIRECTORIES.has(item.path))
  );
}

function isTrashWorkspaceItem(item: WorkspaceFileItemResponse) {
  return item.type === "directory" && item.path === TRASH_DIRECTORY;
}

function isTrashPath(path: string) {
  return path === TRASH_DIRECTORY || path.startsWith(`${TRASH_DIRECTORY}/`);
}

function getParentPath(path: string) {
  const parts = path.split("/").filter(Boolean);
  return parts.slice(0, -1).join("/");
}

function isDirectoryInside(sourcePath: string, targetPath: string) {
  return targetPath === sourcePath || targetPath.startsWith(`${sourcePath}/`);
}

function hasExternalFiles(event: DragEvent<HTMLElement | HTMLDivElement>) {
  return Array.from(event.dataTransfer.types).includes("Files");
}

function hasWorkspaceDrag(event: DragEvent<HTMLElement | HTMLDivElement>) {
  return Array.from(event.dataTransfer.types).includes(WORKSPACE_DRAG_MIME);
}

function findDirectory(items: WorkspaceFileItemResponse[], path: string): WorkspaceFileItemResponse | null {
  for (const item of items) {
    if (item.type === "directory" && item.path === path) return item;
    const child = findDirectory(item.children ?? [], path);
    if (child) return child;
  }
  return null;
}

function getItemsAtPath(items: WorkspaceFileItemResponse[], path: string) {
  if (!path) return items;
  return findDirectory(items, path)?.children ?? [];
}

function makeBreadcrumb(path: string) {
  if (!path) return [];
  const parts = path.split("/");
  return parts.map((name, index) => ({
    name,
    path: parts.slice(0, index + 1).join("/"),
  }));
}

function getFileKind(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["pdf"].includes(ext)) return "pdf";
  if (["ts", "tsx", "js", "jsx", "py", "json", "md", "css", "html"].includes(ext)) return "code";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) return "image";
  if (["mp3", "wav", "m4a", "mp4", "mov", "mkv", "webm"].includes(ext)) return "media";
  if (["eml", "msg", "mbox"].includes(ext)) return "email";
  if (["xlsx", "xls", "csv"].includes(ext)) return "sheet";
  if (["doc", "docx"].includes(ext)) return "doc";
  return "file";
}

function countPendingIngestFiles(items: WorkspaceFileItemResponse[]): number {
  let count = 0;
  for (const item of items) {
    if (item.type === "directory") {
      count += countPendingIngestFiles(item.children ?? []);
      continue;
    }
    const status = item.rag_status ?? "not_indexed";
    if (!["indexed", "skipped"].includes(status)) count += 1;
  }
  return count;
}

function nativeResultCount(payload: Record<string, unknown> | undefined) {
  const result = payload?.result;
  if (Array.isArray(result)) return result.length;
  if (result && typeof result === "object") return Object.keys(result).length;
  return payload?.status === "ok" ? 0 : 0;
}

type NativeContextKind = "graph" | "timeline" | "backlinks";

type NativeContextListItem = {
  id: string;
  title: string;
  subtitle: string;
  detail: string;
};

function nativeText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function nativePick(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = nativeText(record[key]);
    if (value) return value;
  }
  return "";
}

function nativeResultItems(payload: Record<string, unknown> | undefined, kind: NativeContextKind): NativeContextListItem[] {
  const result = payload?.result;
  if (!Array.isArray(result)) return [];
  return result
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    .slice(0, 8)
    .map((item, index) => {
      if (kind === "timeline") {
        const date = nativePick(item, ["date", "created_at", "timestamp"]);
        const summary = nativePick(item, ["summary", "title", "event", "text"]) || `Timeline entry ${index + 1}`;
        const source = nativePick(item, ["source", "source_file", "citation", "page_slug"]);
        const detail = nativePick(item, ["detail", "description", "content"]);
        return {
          id: nativePick(item, ["id"]) || `${kind}-${index}`,
          title: date ? `${date} · ${summary}` : summary,
          subtitle: source || "timeline",
          detail,
        };
      }
      if (kind === "backlinks") {
        const from = nativePick(item, ["from", "from_slug", "from_page", "source_slug", "slug"]);
        const relation = nativePick(item, ["link_type", "relation_type", "type"]);
        const title = nativePick(item, ["title", "from_title", "source_title"]) || from || `Backlink ${index + 1}`;
        const evidence = nativePick(item, ["evidence", "anchor", "context", "to"]);
        return {
          id: nativePick(item, ["id"]) || `${kind}-${index}`,
          title,
          subtitle: [relation, from].filter(Boolean).join(" · ") || "backlink",
          detail: evidence,
        };
      }
      const from = nativePick(item, ["from", "from_slug", "source", "source_slug"]);
      const to = nativePick(item, ["to", "to_slug", "target", "target_slug", "slug"]);
      const relation = nativePick(item, ["link_type", "relation_type", "type"]);
      const depth = nativePick(item, ["depth", "distance"]);
      return {
        id: nativePick(item, ["id"]) || `${kind}-${index}`,
        title: [from, to].filter(Boolean).join(" -> ") || nativePick(item, ["title", "slug"]) || `Graph path ${index + 1}`,
        subtitle: [relation, depth ? `depth ${depth}` : ""].filter(Boolean).join(" · ") || "graph",
        detail: nativePick(item, ["evidence", "summary", "context"]),
      };
    });
}

function graphEventTimestamp(date?: string) {
  if (!date) return null;
  const parsed = Date.parse(date);
  return Number.isNaN(parsed) ? null : parsed;
}

function graphEventGroupLabel(date?: string) {
  const timestamp = graphEventTimestamp(date);
  if (timestamp === null) return "未标日期";
  const value = new Date(timestamp);
  return `${value.getFullYear()}年${String(value.getMonth() + 1).padStart(2, "0")}月`;
}


interface GraphLayoutNode {
  id: string;
  degree: number;
  isFocus: boolean;
  isNeighbor: boolean;
}

interface Position { x: number; y: number }

function graphForceLayout(
  nodes: Array<{ id: string; degree: number; isFocus: boolean; isNeighbor: boolean; entityType?: string }>,
  edges: Array<{ from: string; to: string }>,
  width: number,
  height: number,
  baseRadius: number,
): Map<string, Position> {
  const cx = width / 2;
  const cy = height / 2;
  const positions = new Map<string, Position>();
  const edgeSet = new Set(edges.map((e) => `${e.from}::${e.to}`));

  const maxDegree = Math.max(1, ...nodes.map((n) => n.degree));
  const nodeCount = nodes.length;

  // Build adjacency for component-aware initialization
  const adjacency = new Map<string, Set<string>>();
  for (const edge of edges) {
    let set = adjacency.get(edge.from); if (!set) { set = new Set(); adjacency.set(edge.from, set); } set.add(edge.to);
    set = adjacency.get(edge.to); if (!set) { set = new Set(); adjacency.set(edge.to, set); } set.add(edge.from);
  }

  // Breadth-first ordering from focus node: neighbors first, then by distance
  const visited = new Set<string>();
  const ordered: string[] = [];
  const focusNode = nodes.find((n) => n.isFocus);
  if (focusNode) {
    const queue = [focusNode.id];
    visited.add(focusNode.id);
    while (queue.length > 0) {
      const current = queue.shift()!;
      ordered.push(current);
      for (const neighbor of adjacency.get(current) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
  }
  for (const node of nodes) {
    if (!visited.has(node.id)) ordered.push(node.id);
  }

  const orderMap = new Map(ordered.map((id, i) => [id, i]));

  // Initialize: BFS-order radial, degree-weighted, entity-type ring offset
  const entityTypes = [...new Set(nodes.map((n) => n.entityType ?? "page").filter(Boolean))];
  const entityTypeAngleOffset = new Map(entityTypes.map((type, i) => [type, (i / entityTypes.length) * Math.PI * 0.5]));

  for (const node of nodes) {
    if (node.isFocus) {
      positions.set(node.id, { x: cx, y: cy });
      continue;
    }
    const order = orderMap.get(node.id) ?? 0;
    const total = nodeCount;
    const angle = -Math.PI / 2 + (order / Math.max(1, total)) * Math.PI * 2
      + (entityTypeAngleOffset.get(node.entityType ?? "page") ?? 0);
    const degreeFactor = Math.max(0.3, node.degree / maxDegree);
    const ring = Math.floor(order / Math.max(1, Math.ceil(total / 3)));
    const ringRadius = baseRadius * (0.45 + degreeFactor * 0.55 + ring * 0.12);
    positions.set(node.id, {
      x: cx + Math.cos(angle) * ringRadius,
      y: cy + Math.sin(angle) * ringRadius,
    });
  }

  // Enhanced force-directed relaxation: up to 12 iterations with adaptive cooling
  const iterations = Math.min(12, Math.max(8, nodeCount));
  for (let iter = 0; iter < iterations; iter++) {
    const displacements = new Map<string, { dx: number; dy: number }>();
    for (const node of nodes) {
      displacements.set(node.id, { dx: 0, dy: 0 });
    }

    // Repulsion between all node pairs (O(n^2) simplified)
    for (let i = 0; i < nodeCount; i++) {
      for (let j = i + 1; j < nodeCount; j++) {
        const a = nodes[i], b = nodes[j];
        const posA = positions.get(a.id), posB = positions.get(b.id);
        if (!posA || !posB) continue;
        const dx = posA.x - posB.x, dy = posA.y - posB.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const connected = edgeSet.has(`${a.id}::${b.id}`) || edgeSet.has(`${b.id}::${a.id}`);
        // Connected attraction, disconnected repulsion
        const forceMagnitude = connected
          ? -Math.sqrt(dist) * 0.18
          : (baseRadius * 3.0) / (dist * dist);
        const force = forceMagnitude;
        const dispA = displacements.get(a.id)!;
        const dispB = displacements.get(b.id)!;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        dispA.dx += fx; dispA.dy += fy;
        dispB.dx -= fx; dispB.dy -= fy;
      }
    }

    // Same-entity-type weak attraction (clusters similar nodes)
    for (let i = 0; i < nodeCount; i++) {
      for (let j = i + 1; j < nodeCount; j++) {
        const a = nodes[i], b = nodes[j];
        if (a.isFocus || b.isFocus) continue;
        if (a.entityType !== b.entityType || !a.entityType) continue;
        const posA = positions.get(a.id), posB = positions.get(b.id);
        if (!posA || !posB) continue;
        const dx = posA.x - posB.x, dy = posA.y - posB.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const attract = dist * 0.004;
        const dispA = displacements.get(a.id)!;
        const dispB = displacements.get(b.id)!;
        dispA.dx -= (dx / dist) * attract;
        dispA.dy -= (dy / dist) * attract;
        dispB.dx += (dx / dist) * attract;
        dispB.dy += (dy / dist) * attract;
      }
    }

    // Center gravity: mild pull for non-focus, stronger for focus-neighbors
    for (const node of nodes) {
      if (node.isFocus) continue;
      const pos = positions.get(node.id)!;
      const disp = displacements.get(node.id)!;
      const dx = cx - pos.x, dy = cy - pos.y;
      const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const gravity = node.isNeighbor ? 0.12 : 0.06;
      disp.dx += (dx / dist) * gravity;
      disp.dy += (dy / dist) * gravity;
    }

    // Apply displacements with adaptive cooling
    let maxDisp = 0;
    const cooling = 1 / Math.sqrt(iter + 1);
    for (const node of nodes) {
      if (node.isFocus) continue;
      const pos = positions.get(node.id)!;
      const disp = displacements.get(node.id)!;
      const mag = Math.sqrt(disp.dx * disp.dx + disp.dy * disp.dy);
      maxDisp = Math.max(maxDisp, mag);
      const clamp = Math.min(mag, baseRadius * 0.4) / Math.max(1, mag);
      pos.x += disp.dx * clamp * cooling;
      pos.y += disp.dy * clamp * cooling;
      pos.x = Math.max(20, Math.min(width - 20, pos.x));
      pos.y = Math.max(20, Math.min(height - 20, pos.y));
    }
    if (maxDisp < 0.25 && iter > 3) break;
  }

  return positions;
}

function graphEntityTypeColor(entityType: string): string {
  const palette: Record<string, string> = {
    client_profile: "#4f46e5",
    client_profile_unresolved: "#818cf8",
    customer_project: "#0891b2",
    customer_project_profile_unresolved: "#22d3ee",
    customer_company: "#059669",
    customer_company_profile_unresolved: "#34d399",
    project: "#d97706",
    event: "#dc2626",
    source_event: "#dc2626",
    customer_source_event_unresolved: "#f87171",
    meeting: "#9333ea",
    page: "#6b7280",
    unresolved_entity: "#9ca3af",
  };
  const key = (entityType ?? "page").toLowerCase();
  for (const [prefix, color] of Object.entries(palette)) {
    if (key.includes(prefix)) return color;
  }
  return palette.page;
}

function graphCanvasPointSized(
  index: number,
  total: number,
  hasFocusNode: boolean,
  width: number,
  height: number,
  baseRadius: number,
  // New params for force layout
  _nodes?: Array<{ id: string; degree: number; isFocus: boolean; isNeighbor: boolean }>,
  _edges?: Array<{ from: string; to: string }>,
) {
  // Fallback: simple radial when no graph data is available (for existing call sites)
  const centerX = width / 2;
  const centerY = height / 2;
  if ((hasFocusNode && index === 0) || (!hasFocusNode && total === 1)) {
    return { x: centerX, y: centerY };
  }
  const ringIndex = hasFocusNode ? index - 1 : index;
  const ringTotal = Math.max(1, hasFocusNode ? total - 1 : total);
  const angle = -Math.PI / 2 + (ringIndex / ringTotal) * Math.PI * 2;
  const radius = ringTotal > 8 && ringIndex % 2 === 1 ? baseRadius * 1.22 : baseRadius;
  return {
    x: centerX + Math.cos(angle) * radius,
    y: centerY + Math.sin(angle) * radius,
  };
}

function graphCanvasPoint(index: number, total: number, hasFocusNode: boolean) {
  return graphCanvasPointSized(index, total, hasFocusNode, 340, 216, 72);
}

function graphCanvasLabel(value: string) {
  const text = value.trim();
  return text.length > 12 ? `${text.slice(0, 11)}...` : text;
}

function graphCanvasLargeLabel(value: string) {
  const text = value.trim();
  return text.length > 18 ? `${text.slice(0, 17)}...` : text;
}

function clampGraphCanvasScale(value: number) {
  return Math.max(0.7, Math.min(2.4, value));
}


function graphCitationString(citation: Record<string, unknown> | null | undefined, key: string) {
  const value = citation?.[key];
  return typeof value === "string" ? value.trim() : "";
}

function normalizeGraphSourcePath(value: string | null | undefined) {
  const text = (value ?? "").trim().replace(/\\/g, "/");
  if (!text || text.startsWith("/") || /^[A-Za-z]:\//.test(text) || text.includes("..")) return "";
  const first = text.split("/")[0]?.toLowerCase() ?? "";
  if ([".git", ".trash", "derived", "manifests", ".pending_review"].includes(first)) return "";
  return text;
}

function graphPreviewSourcePath(
  item: { source_file?: string | null; citation?: Record<string, unknown> | null } | null | undefined,
) {
  if (!item) return "";
  return (
    normalizeGraphSourcePath(item.source_file)
    || normalizeGraphSourcePath(graphCitationString(item.citation, "source_file"))
  );
}

function agentRunStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待输入";
  if (status === "queued") return "排队中";
  return "执行中";
}

function renderWorkspaceAgentRun(run: AgentRunResponse) {
  return (
    <div className={`message-agent-run-card workspace-agent-run-card is-${run.status}`}>
      <div className="message-agent-run-header">
        <span className="message-agent-run-icon"><AgentIcon /></span>
        <div>
          <strong>{run.title}</strong>
          <span>{agentRunStatusLabel(run.status)}</span>
        </div>
      </div>
      {run.events?.length ? (
        <ol className="message-agent-event-list">
          {run.events.map((event) => (
            <li className={`message-agent-event is-${event.status}`} key={event.id}>
              <span className="message-agent-event-dot" />
              <div>
                <div className="message-agent-event-title">
                  <strong>{event.title}</strong>
                  <small>{event.status}</small>
                </div>
                {event.detail ? <p>{event.detail}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      {run.error_message ? (
        <p className="message-agent-run-error">
          {run.error_message}。请检查文件权限、网络或 GBrain 服务状态后重新执行。
        </p>
      ) : null}
    </div>
  );
}

export function WorkspaceFilePanel({ apiOptions, workspaceId, workspaceName, workspaceKind = "project", canIngestKnowledge = false, defaultPath = "", onReferenceFile, onPreviewOpen }: WorkspaceFilePanelProps) {
  const [items, setItems] = useState<WorkspaceFileItemResponse[]>([]);
  const [currentPath, setCurrentPath] = useState(defaultPath);
  const [history, setHistory] = useState<string[]>([defaultPath || ""]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"files" | "trash">("files");
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [latestAgentRun, setLatestAgentRun] = useState<AgentRunResponse | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<WorkspaceConfirmation | null>(null);
  const [confirmationBusy, setConfirmationBusy] = useState(false);
  const [filePreview, setFilePreview] = useState<WorkspaceFilePreview | null>(null);
  const [knowledgeGraph, setKnowledgeGraph] = useState<WorkspaceKnowledgeGraphResponse | null>(null);
  const [knowledgeGraphOpen, setKnowledgeGraphOpen] = useState(false);
  const [knowledgeGraphCanvasOpen, setKnowledgeGraphCanvasOpen] = useState(false);
  const [knowledgeGraphCanvasView, setKnowledgeGraphCanvasView] = useState({ x: 0, y: 0, scale: 1 });
  const [knowledgeGraphCanvasPanning, setKnowledgeGraphCanvasPanning] = useState(false);
  const [knowledgeGraphLoading, setKnowledgeGraphLoading] = useState(false);
  const [knowledgeGraphError, setKnowledgeGraphError] = useState<string | null>(null);
  const [graphSearchTerm, setGraphSearchTerm] = useState("");
  const [graphEntityFilter, setGraphEntityFilter] = useState("all");
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [selectedGraphEventId, setSelectedGraphEventId] = useState<string | null>(null);
  const [graphTimelineFilter, setGraphTimelineFilter] = useState<"all" | "dated" | "undated" | "selected">("all");
  const [graphTimelineDensity, setGraphTimelineDensity] = useState<"detail" | "compact" | "axis">("detail");
  const [collapsedTimelineGroups, setCollapsedTimelineGroups] = useState<Set<string>>(() => new Set());
  const [entityMergeCandidates, setEntityMergeCandidates] = useState<WorkspaceEntityMergeCandidatesResponse | null>(null);
  const [entityMergePreview, setEntityMergePreview] = useState<GBrainEntityMergePreviewResponse | null>(null);
  const [entityMergeLoading, setEntityMergeLoading] = useState(false);
  const [entityMergeMessage, setEntityMergeMessage] = useState<string | null>(null);
  const [nativeGraphContext, setNativeGraphContext] = useState<WorkspaceNativeGraphContextResponse | null>(null);
  const [nativeGraphLoadingSlug, setNativeGraphLoadingSlug] = useState<string | null>(null);
  const [nativeGraphMessage, setNativeGraphMessage] = useState<string | null>(null);
  const [refreshingKnowledge, setRefreshingKnowledge] = useState(false);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<WorkspaceFileContextMenu | null>(null);
  const [clipboardItem, setClipboardItem] = useState<WorkspaceClipboardItem | null>(null);
  const [draggedItem, setDraggedItem] = useState<WorkspaceFileItemResponse | null>(null);
  const [dropTargetPath, setDropTargetPath] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState({ active: false, current: 0, total: 0, filename: "" });
  const [compactActions, setCompactActions] = useState(false);
  const [previewWidth, setPreviewWidth] = useState(readPreviewWidth);
  const [previewResizing, setPreviewResizing] = useState(false);
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const previewObjectUrlRef = useRef<string | null>(null);
  const graphCanvasPanRef = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);

  const displayItems = useMemo(() => filterSystemWorkspaceItems(items), [items]);
  const visibleItems = useMemo(() => viewMode === "trash" ? items : getItemsAtPath(displayItems, currentPath), [currentPath, displayItems, items, viewMode]);
  const breadcrumb = useMemo(() => makeBreadcrumb(currentPath), [currentPath]);
  const pendingIngestCount = useMemo(() => countPendingIngestFiles(displayItems), [displayItems]);

  function navigateTo(path: string) {
    if (path === currentPath) return;
    closeFilePreview();
    setCurrentPath(path);
    setHistory((prev) => {
      const next = [...prev.slice(0, historyIndex + 1), path];
      setHistoryIndex(next.length - 1);
      return next;
    });
  }

  function goBack() {
    if (historyIndex <= 0) return;
    const nextIndex = historyIndex - 1;
    setHistoryIndex(nextIndex);
    setCurrentPath(history[nextIndex] ?? "");
  }

  function goForward() {
    if (historyIndex >= history.length - 1) return;
    const nextIndex = historyIndex + 1;
    setHistoryIndex(nextIndex);
    setCurrentPath(history[nextIndex] ?? "");
  }

  function goUp() {
    if (!currentPath) return;
    navigateTo(currentPath.split("/").slice(0, -1).join("/"));
  }

  function refresh() {
    if (!workspaceId) {
      setItems([]);
      setCurrentPath("");
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return listWorkspaceFiles(apiOptions, workspaceId, viewMode === "trash")
      .then((response) => {
        setItems(response.items);
        const safeItems = filterSystemWorkspaceItems(response.items);
        if (viewMode === "files" && currentPath && !findDirectory(safeItems, currentPath)) {
          navigateTo("");
        }
      })
      .catch((loadError: unknown) => {
        setError(loadError instanceof Error ? loadError.message : "无法读取项目文件目录");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    void refresh();
  }, [apiOptions, workspaceId, viewMode]);

  useEffect(() => {
    if (viewMode !== "files") return;
    const nextPath = defaultPath || "";
    setCurrentPath(nextPath);
    setHistory([nextPath]);
    setHistoryIndex(0);
  }, [defaultPath, workspaceId, viewMode]);

  useEffect(() => {
    if (viewMode !== "files" || !currentPath || loading) return;
    if (!findDirectory(displayItems, currentPath)) {
      setCurrentPath("");
      setHistory([""]);
      setHistoryIndex(0);
    }
  }, [currentPath, displayItems, loading, viewMode]);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel || typeof ResizeObserver === "undefined") return;
    const updateCompactState = () => {
      setCompactActions(panel.getBoundingClientRect().width <= 420);
    };
    updateCompactState();
    const observer = new ResizeObserver(updateCompactState);
    observer.observe(panel);
    return () => observer.disconnect();
  }, []);

  const hasSidecar = Boolean(filePreview || knowledgeGraphOpen);

  useEffect(() => {
    if (!hasSidecar) return;
    const layout = layoutRef.current;
    if (!layout || typeof ResizeObserver === "undefined") return;
    const updatePreviewWidth = () => {
      setPreviewWidth((width) => clampPreviewWidth(width, layout.getBoundingClientRect().width));
    };
    updatePreviewWidth();
    const observer = new ResizeObserver(updatePreviewWidth);
    observer.observe(layout);
    return () => observer.disconnect();
  }, [hasSidecar]);

  useEffect(() => {
    if (!hasSidecar) return;
    setPreviewWidth((width) => clampPreviewWidth(Math.max(width, PREVIEW_DEFAULT_WIDTH), layoutRef.current?.getBoundingClientRect().width));
  }, [filePreview?.item.path, hasSidecar]);

  useEffect(() => {
    writePreviewWidth(previewWidth);
  }, [previewWidth]);

  useEffect(() => {
    if (!previewResizing) return;

    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const layout = layoutRef.current;
      if (!layout) return;
      const rect = layout.getBoundingClientRect();
      setPreviewWidth(clampPreviewWidth(rect.right - event.clientX, rect.width));
    }

    function handleMouseUp() {
      setPreviewResizing(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [previewResizing]);

  useEffect(() => {
    if (!knowledgeGraphCanvasPanning) return;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "grabbing";
    document.body.style.userSelect = "none";

    function handleMouseMove(event: globalThis.MouseEvent) {
      const drag = graphCanvasPanRef.current;
      if (!drag) return;
      setKnowledgeGraphCanvasView((view) => ({
        ...view,
        x: drag.originX + (event.clientX - drag.startX) / Math.max(0.7, view.scale),
        y: drag.originY + (event.clientY - drag.startY) / Math.max(0.7, view.scale),
      }));
    }

    function handleMouseUp() {
      graphCanvasPanRef.current = null;
      setKnowledgeGraphCanvasPanning(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [knowledgeGraphCanvasPanning]);

  useEffect(() => {
    function closeFloatingMenus() {
      setActionMenuOpen(false);
      setContextMenu(null);
    }

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") closeFloatingMenus();
    }

    document.addEventListener("click", closeFloatingMenus);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("click", closeFloatingMenus);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
        previewObjectUrlRef.current = null;
      }
    };
  }, []);

  async function handleUpload(fileList: FileList | File[] | null, directory = currentPath) {
    const files = Array.from(fileList ?? []);
    if (!workspaceId || files.length === 0) return;
    if (isTrashPath(directory)) {
      setError("回收站不能直接上传文件");
      return;
    }
    setError(null);
    setNotice(null);
    setUploadProgress({ active: true, current: 0, total: files.length, filename: files[0]?.name ?? "" });
    try {
      const response = await uploadWorkspaceFiles(apiOptions, workspaceId, directory, files);
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setUploadProgress({ active: true, current: files.length, total: files.length, filename: files[files.length - 1]?.name ?? "" });
      await refresh();
    } catch (uploadError: unknown) {
      setError(uploadError instanceof Error ? uploadError.message : "上传失败");
    } finally {
      window.setTimeout(() => setUploadProgress({ active: false, current: 0, total: 0, filename: "" }), 350);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleCreateFolder(parentPath = currentPath) {
    if (!workspaceId) return;
    if (isTrashPath(parentPath)) {
      setError("回收站不能新建文件夹");
      return;
    }
    const name = window.prompt("新建文件夹名称");
    if (!name?.trim()) return;
    try {
      const response = await createWorkspaceFolder(apiOptions, workspaceId, { parent_path: parentPath, name });
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      await refresh();
    } catch (createError: unknown) {
      setError(createError instanceof Error ? createError.message : "新建文件夹失败");
    }
  }

  async function handleRename(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    if (!canModifyWorkspaceItem(item)) {
      setError("只有上传人或管理员可以修改该文件");
      return;
    }
    const name = window.prompt("重命名", item.name);
    if (!name?.trim() || name.trim() === item.name) return;
    try {
      const response = await renameWorkspacePath(apiOptions, workspaceId, { path: item.path, new_name: name.trim() });
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      await refresh();
    } catch (renameError: unknown) {
      setError(renameError instanceof Error ? renameError.message : "重命名失败");
    }
  }

  async function executeMove(item: WorkspaceFileItemResponse, targetDirectory: string) {
    if (!workspaceId) return;
    if (!canModifyWorkspaceItem(item)) {
      setError("只有上传人或管理员可以修改该文件");
      return;
    }
    if (!canMoveItemTo(item, targetDirectory)) return;
    try {
      const response = await moveWorkspacePath(apiOptions, workspaceId, { path: item.path, target_directory: targetDirectory, conflict_strategy: "keep_both" });
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`已移动「${item.name}」。`);
      if (filePreview?.item.path === item.path) closeFilePreview();
      await refresh();
    } catch (moveError: unknown) {
      setError(moveError instanceof Error ? moveError.message : "移动失败");
    }
  }

  async function executeCopy(item: WorkspaceFileItemResponse, targetDirectory: string) {
    if (!workspaceId) return;
    if (!canCopyWorkspaceItem(item)) {
      setError("默认项目目录不能复制");
      return;
    }
    try {
      const response = await copyWorkspacePath(apiOptions, workspaceId, { path: item.path, target_directory: targetDirectory, conflict_strategy: "keep_both" });
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`已复制「${item.name}」。`);
      await refresh();
    } catch (copyError: unknown) {
      setError(copyError instanceof Error ? copyError.message : "复制失败");
    }
  }

  function handleCut(item: WorkspaceFileItemResponse) {
    if (!canModifyWorkspaceItem(item)) {
      setError("只有上传人或管理员可以修改该文件");
      return;
    }
    setClipboardItem({ action: "cut", item });
    setNotice(`已剪切「${item.name}」，请选择目标文件夹后粘贴。`);
  }

  function handleCopy(item: WorkspaceFileItemResponse) {
    if (!canCopyWorkspaceItem(item)) {
      setError("默认项目目录不能复制");
      return;
    }
    setClipboardItem({ action: "copy", item });
    setNotice(`已复制「${item.name}」，请选择目标文件夹后粘贴。`);
  }

  async function handlePaste(targetDirectory = currentPath) {
    if (!clipboardItem) return;
    if (isTrashPath(targetDirectory)) {
      setError("回收站不能作为粘贴目标");
      return;
    }
    if (clipboardItem.action === "cut") {
      await executeMove(clipboardItem.item, targetDirectory);
      setClipboardItem(null);
      return;
    }
    await executeCopy(clipboardItem.item, targetDirectory);
  }

  async function handleDelete(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    if (!item.can_delete && item.type !== "directory") {
      setError("只有上传人或管理员可以删除该文件");
      return;
    }
    setPendingConfirmation({
      title: item.type === "directory" ? "删除项目文件夹" : "移入项目回收区",
      detail: item.type === "directory" ? `将删除空文件夹「${item.name}」。` : `将「${item.name}」移入回收区，项目知识状态会重新标记为待录入。`,
      confirmLabel: item.type === "directory" ? "删除文件夹" : "移入回收区",
      tone: "warning",
      onConfirm: async () => {
        if (item.type === "directory") {
          const response = await deleteWorkspaceFolder(apiOptions, workspaceId, item.path);
          if (response.agent_run) setLatestAgentRun(response.agent_run);
          if (currentPath.startsWith(`${item.path}/`)) navigateTo("");
        } else {
          const response = await deleteWorkspaceFile(apiOptions, workspaceId, item.path);
          if (response.agent_run) setLatestAgentRun(response.agent_run);
        }
        await refresh();
      },
    });
  }

  async function handleRestore(item: WorkspaceFileItemResponse) {
    if (!workspaceId || !item.id) return;
    try {
      const response = await restoreWorkspaceFile(apiOptions, workspaceId, item.id);
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      await refresh();
    } catch (restoreError: unknown) {
      setError(restoreError instanceof Error ? restoreError.message : "恢复失败");
    }
  }

  async function handlePermanentDelete(item: WorkspaceFileItemResponse) {
    if (!workspaceId || !item.id) return;
    setPendingConfirmation({
      title: "永久删除项目文件",
      detail: `将永久删除「${item.name}」。此操作不可恢复，且会触发项目知识状态重新计算。`,
      confirmLabel: "永久删除",
      tone: "danger",
      onConfirm: async () => {
        const response = await permanentlyDeleteWorkspaceFile(apiOptions, workspaceId, item.id!);
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
  }

  async function handleRefreshKnowledge() {
    if (!workspaceId) return;
    const storeLabel = knowledgeStoreLabel(workspaceKind);
    setRefreshingKnowledge(true);
    setError(null);
    setNotice(null);
    try {
      const queued = await enqueueWorkspaceKnowledgeIngest(apiOptions, workspaceId);
      setLatestAgentRun(queued.agent_run ?? null);
      setNotice(`${storeLabel}录入已进入后台队列：任务 #${queued.id}。`);
      let job = queued;
      for (let attempt = 0; attempt < 120 && ["queued", "running"].includes(job.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        job = await getWorkspaceKnowledgeIngestJob(apiOptions, workspaceId, queued.id);
        if (job.agent_run) setLatestAgentRun(job.agent_run);
      }
      if (["queued", "running"].includes(job.status)) {
        setNotice(`${storeLabel}录入仍在后台执行：任务 #${queued.id}，完成后会通知你。`);
        return;
      }
      const result = job.result;
      if (job.agent_run) setLatestAgentRun(job.agent_run);
      if (!result.ok) {
        const detail = job.error_message || result.gbrain_error || result.gbrain_status || "工作区资料已处理，但 GBrain source 尚未完成同步";
        setError(`录入未完成：${detail}`);
      } else {
        const parts = [
          `已入库 ${result.indexed_files ?? 0} 个`,
          `待能力补齐 ${result.pending_extractor_capability_files ?? 0} 个`,
          `待转写 ${result.pending_transcription_files ?? 0} 个`,
        ];
        if ((result.failed_files ?? 0) > 0) parts.push(`失败 ${result.failed_files} 个`);
        setNotice(`${storeLabel}录入完成：${parts.join("，")}。`);
      }
      await refresh();
    } catch (refreshError: unknown) {
      setError(refreshError instanceof Error ? refreshError.message : `录入${storeLabel}失败`);
    } finally {
      setRefreshingKnowledge(false);
    }
  }

  async function handleClearTrash() {
    if (!workspaceId) return;
    setPendingConfirmation({
      title: "清空项目回收区",
      detail: "将永久删除当前可清理的回收区文件。此操作不可恢复。",
      confirmLabel: "清空回收区",
      tone: "danger",
      onConfirm: async () => {
        const response = await clearWorkspaceTrash(apiOptions, workspaceId);
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
  }

  async function handleConfirmAction() {
    if (!pendingConfirmation || confirmationBusy) return;
    setConfirmationBusy(true);
    setError(null);
    try {
      await pendingConfirmation.onConfirm();
      setPendingConfirmation(null);
    } catch (confirmError: unknown) {
      setError(confirmError instanceof Error ? confirmError.message : "操作失败");
    } finally {
      setConfirmationBusy(false);
    }
  }

  function closeFilePreview() {
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    setFilePreview(null);
  }

  async function openFilePreview(item: WorkspaceFileItemResponse) {
    if (!workspaceId || item.type === "directory") return;
    onPreviewOpen?.();
    setKnowledgeGraphOpen(false);
    setKnowledgeGraphCanvasOpen(false);
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
    const kind = getFileKind(item.name);
    setFilePreview({ item, kind, status: "loading" });
    try {
      const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
      if (kind === "image" || kind === "pdf") {
        const objectUrl = URL.createObjectURL(blob);
        previewObjectUrlRef.current = objectUrl;
        setFilePreview({ item, kind, status: "ready", objectUrl });
        return;
      }
      if (kind === "code" || item.name.toLowerCase().endsWith(".txt") || item.name.toLowerCase().endsWith(".md")) {
        const text = await blob.text();
        setFilePreview({ item, kind, status: "ready", text: text.slice(0, 60_000) });
        return;
      }
      const objectUrl = URL.createObjectURL(blob);
      previewObjectUrlRef.current = objectUrl;
      setFilePreview({ item, kind, status: "ready", objectUrl });
    } catch (previewError: unknown) {
      setFilePreview({
        item,
        kind,
        status: "failed",
        error: previewError instanceof Error ? previewError.message : "文件预览失败",
      });
    }
  }

  async function openGraphSourcePreview(sourcePath: string) {
    const normalized = normalizeGraphSourcePath(sourcePath);
    if (!normalized) {
      setNativeGraphMessage("该 citation 未指向可直接预览的工作区源文件。");
      return;
    }
    const name = normalized.split("/").filter(Boolean).pop() || normalized;
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

  function handlePreviewResizeStart(event: MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setPreviewResizing(true);
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
      setNativeGraphMessage(result.status === "ok" ? "GBrain 原生图谱上下文已加载。" : result.error || "GBrain 原生图谱上下文加载失败。");
    } catch (nativeError: unknown) {
      setNativeGraphMessage(nativeError instanceof Error ? nativeError.message : "GBrain 原生图谱上下文加载失败");
    } finally {
      setNativeGraphLoadingSlug(null);
    }
  }

  function closeKnowledgeGraph() {
    setKnowledgeGraphOpen(false);
    setKnowledgeGraphCanvasOpen(false);
  }

  function resetKnowledgeGraphCanvasView() {
    setKnowledgeGraphCanvasView({ x: 0, y: 0, scale: 1 });
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

  function zoomKnowledgeGraphCanvas(delta: number) {
    setKnowledgeGraphCanvasView((view) => ({
      ...view,
      scale: clampGraphCanvasScale(view.scale + delta),
    }));
  }

  function handleKnowledgeGraphCanvasWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.12 : 0.12;
    zoomKnowledgeGraphCanvas(delta);
  }

  function handleKnowledgeGraphCanvasPanStart(event: MouseEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const target = event.target;
    if (target instanceof Element && target.closest(".workspace-knowledge-map-node, button")) return;
    event.preventDefault();
    graphCanvasPanRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: knowledgeGraphCanvasView.x,
      originY: knowledgeGraphCanvasView.y,
    };
    setKnowledgeGraphCanvasPanning(true);
  }

  function activateFileItem(item: WorkspaceFileItemResponse) {
    if (isTrashWorkspaceItem(item)) {
      setViewMode("trash");
      navigateTo("");
      return;
    }
    if (item.type === "directory") {
      navigateTo(item.path);
      return;
    }
    void openFilePreview(item);
  }

  function handleFileItemKeyDown(event: KeyboardEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activateFileItem(item);
  }

  function canModifyWorkspaceItem(item: WorkspaceFileItemResponse) {
    if (isProtectedWorkspaceDirectory(item, workspaceKind)) return false;
    return item.type === "directory" || item.can_delete;
  }

  function canCopyWorkspaceItem(item: WorkspaceFileItemResponse) {
    return !isProtectedWorkspaceDirectory(item, workspaceKind);
  }

  function canMoveItemTo(item: WorkspaceFileItemResponse, targetDirectory: string) {
    if (isTrashWorkspaceItem(item) || isTrashPath(targetDirectory)) return false;
    if (!canModifyWorkspaceItem(item)) return false;
    if (getParentPath(item.path) === targetDirectory) return false;
    if (item.type === "directory" && isDirectoryInside(item.path, targetDirectory)) return false;
    return true;
  }

  function canPasteInto(targetDirectory: string) {
    if (!clipboardItem) return false;
    if (isTrashPath(targetDirectory)) return false;
    if (clipboardItem.action === "cut") return canMoveItemTo(clipboardItem.item, targetDirectory);
    if (!canCopyWorkspaceItem(clipboardItem.item)) return false;
    if (clipboardItem.item.type === "directory" && isDirectoryInside(clipboardItem.item.path, targetDirectory)) return false;
    return true;
  }

  function openFileContextMenu(event: MouseEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) {
    event.preventDefault();
    event.stopPropagation();
    const menuWidth = 176;
    const menuHeight = item.type === "directory" ? 280 : 250;
    const x = Math.min(event.clientX, window.innerWidth - menuWidth - 8);
    const y = Math.min(event.clientY, window.innerHeight - menuHeight - 8);
    setActionMenuOpen(false);
    setContextMenu({ item, x: Math.max(8, x), y: Math.max(8, y) });
  }

  function runContextAction(action: () => void) {
    setContextMenu(null);
    action();
  }

  function handleFileDragStart(event: DragEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) {
    if (!canModifyWorkspaceItem(item)) {
      event.preventDefault();
      return;
    }
    setDraggedItem(item);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(WORKSPACE_DRAG_MIME, item.path);
    event.dataTransfer.setData("text/plain", item.path);
  }

  function handleFileDragEnd() {
    setDraggedItem(null);
    setDropTargetPath(null);
  }

  function handleDirectoryDragOver(event: DragEvent<HTMLDivElement | HTMLButtonElement>, targetPath: string) {
    if (isTrashPath(targetPath)) return;
    if (!draggedItem || !hasWorkspaceDrag(event) || !canMoveItemTo(draggedItem, targetPath)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    setDragOver(false);
    setDropTargetPath(targetPath);
  }

  async function handleDirectoryDrop(event: DragEvent<HTMLDivElement | HTMLButtonElement>, targetPath: string) {
    event.preventDefault();
    event.stopPropagation();
    setDragOver(false);
    setDropTargetPath(null);
    if (isTrashPath(targetPath)) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) {
      await handleUpload(files, targetPath);
      return;
    }
    if (!draggedItem || !canMoveItemTo(draggedItem, targetPath)) return;
    await executeMove(draggedItem, targetPath);
    setDraggedItem(null);
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();
    setDragOver(false);
    setDropTargetPath(null);
    if (draggedItem && hasWorkspaceDrag(event)) {
      if (canMoveItemTo(draggedItem, currentPath)) void executeMove(draggedItem, currentPath);
      setDraggedItem(null);
      return;
    }
    void handleUpload(Array.from(event.dataTransfer.files), currentPath);
  }

  const percent = uploadProgress.total > 0 ? Math.round((uploadProgress.current / uploadProgress.total) * 100) : 0;
  const isPersonalWorkspace = workspaceKind === "user";
  const isCustomerWorkspace = workspaceKind === "customer";
  const panelSubtitle = viewMode === "trash" ? "回收站" : isPersonalWorkspace ? "个人文件" : isCustomerWorkspace ? "客户资料" : "项目资料";
  const rootTitle = isPersonalWorkspace ? "个人文件根目录" : isCustomerWorkspace ? "客户资料根目录" : "项目资料根目录";
  const canShowKnowledgeIngest = !isPersonalWorkspace && canIngestKnowledge;
  const canShowKnowledgeGraph = workspaceKind === "project" || workspaceKind === "customer";
  const canShowEntityMergeReview = canShowKnowledgeGraph && canIngestKnowledge;
  const knowledgeGraphLabel = isCustomerWorkspace ? "客户画像" : "事件图谱";
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
  const canvasGraphForceNodes = canvasGraphNodes.map((node, idx) => ({
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
  const largeGraphForceNodes = largeGraphNodes.map((node, idx) => ({
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
    { key: "graph", title: "Graph traversal", items: nativeResultItems(nativeGraphContext.traverse_graph, "graph") },
    { key: "timeline", title: "Timeline", items: nativeResultItems(nativeGraphContext.timeline, "timeline") },
    { key: "backlinks", title: "Backlinks", items: nativeResultItems(nativeGraphContext.backlinks, "backlinks") },
  ] : [];

  return (
    <div
      className={`workspace-file-panel-layout ${hasSidecar ? "has-preview" : ""}`}
      ref={layoutRef}
      style={hasSidecar ? { gridTemplateColumns: `minmax(300px, 1fr) ${previewWidth}px` } : undefined}
    >
    <section
      className={`agent-file-panel ${dragOver ? "is-drag-over" : ""} ${compactActions ? "is-compact-actions" : ""}`}
      onDragLeave={() => {
        setDragOver(false);
        setDropTargetPath(null);
      }}
      onDragOver={(event) => {
        if (draggedItem && hasWorkspaceDrag(event)) {
          if (canMoveItemTo(draggedItem, currentPath)) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            setDropTargetPath(currentPath);
          }
          return;
        }
        if (hasExternalFiles(event)) {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          setDragOver(true);
        }
      }}
      onDrop={handleDrop}
      ref={panelRef}
    >
      <header className="agent-file-panel-header">
        <span className="agent-file-panel-icon"><WorkspaceIcon /></span>
        <div>
          <h2>{workspaceName ?? "当前工作区"}</h2>
          <p>{panelSubtitle}</p>
        </div>
        <div className="agent-file-panel-actions">
          <input className="hidden-file-input" multiple onChange={(event) => void handleUpload(event.target.files)} ref={fileInputRef} type="file" />
          {viewMode === "files" ? (
            <>
              <button aria-label="上传文件" className="workspace-file-primary-action" onClick={() => fileInputRef.current?.click()} title="上传文件" type="button"><PlusIcon /><span>上传</span></button>
              <button aria-label="新建文件夹" className="workspace-file-primary-action" onClick={() => void handleCreateFolder()} title="新建文件夹" type="button"><WorkspaceIcon /><span>新建</span></button>
              <span className="workspace-file-action-menu-wrap" onClick={(event) => event.stopPropagation()}>
                <button aria-expanded={actionMenuOpen} aria-label="更多文件操作" className="workspace-file-action" onClick={() => setActionMenuOpen((value) => !value)} title="更多文件操作" type="button"><MoreIcon /></button>
                {actionMenuOpen ? (
                  <div className="workspace-file-action-menu">
                    <button disabled={loading} onClick={() => { setActionMenuOpen(false); void refresh(); }} type="button"><RefreshIcon />刷新目录</button>
                    <button disabled={!canPasteInto(currentPath)} onClick={() => { setActionMenuOpen(false); void handlePaste(currentPath); }} type="button"><CopyIcon />粘贴到当前文件夹</button>
                    {canShowKnowledgeIngest ? (
                      <button disabled={refreshingKnowledge || pendingIngestCount === 0} onClick={() => { setActionMenuOpen(false); void handleRefreshKnowledge(); }} type="button"><RefreshIcon />{refreshingKnowledge ? "正在录入..." : `一键录入${pendingIngestCount > 0 ? ` (${pendingIngestCount})` : ""}`}</button>
                    ) : null}
                    {canShowKnowledgeGraph ? (
                      <button disabled={knowledgeGraphLoading} onClick={() => { setActionMenuOpen(false); void handleOpenKnowledgeGraph(); }} type="button"><BrainIcon />{knowledgeGraphLoading ? "正在加载..." : knowledgeGraphLabel}</button>
                    ) : null}
                    <button onClick={() => { setActionMenuOpen(false); setViewMode("trash"); navigateTo(""); }} type="button"><TrashIcon />回收站</button>
                  </div>
                ) : null}
              </span>
            </>
          ) : (
            <>
              <button aria-label={isPersonalWorkspace ? "返回个人文件" : "返回项目文件"} className="workspace-file-primary-action" onClick={() => { setViewMode("files"); navigateTo(""); }} title={isPersonalWorkspace ? "个人文件" : "项目文件"} type="button"><WorkspaceIcon /><span>文件</span></button>
              <span className="workspace-file-action-menu-wrap" onClick={(event) => event.stopPropagation()}>
                <button aria-expanded={actionMenuOpen} aria-label="更多回收区操作" className="workspace-file-action" onClick={() => setActionMenuOpen((value) => !value)} title="更多回收区操作" type="button"><MoreIcon /></button>
                {actionMenuOpen ? (
                  <div className="workspace-file-action-menu">
                    <button disabled={loading} onClick={() => { setActionMenuOpen(false); void refresh(); }} type="button"><RefreshIcon />刷新目录</button>
                    <button onClick={() => { setActionMenuOpen(false); void handleClearTrash(); }} type="button"><TrashIcon />清空回收区</button>
                  </div>
                ) : null}
              </span>
            </>
          )}
        </div>
      </header>

      {viewMode === "files" ? (
        <nav className="workspace-file-breadcrumb" aria-label={isPersonalWorkspace ? "个人文件路径" : "项目文件路径"}>
          <div className="workspace-file-nav-controls" aria-label="文件导航" role="group">
            <button aria-label="后退" className="workspace-file-action" disabled={historyIndex <= 0} onClick={goBack} title="后退" type="button"><ChevronLeftIcon /></button>
            <button aria-label="前进" className="workspace-file-action" disabled={historyIndex >= history.length - 1} onClick={goForward} title="前进" type="button"><ChevronRightIcon /></button>
            <button aria-label="上一级" className="workspace-file-action" disabled={!currentPath} onClick={goUp} title="上一级" type="button"><ArrowUpIcon /></button>
          </div>
          <div className="workspace-file-address-bar">
            <button
              aria-label="根目录"
              className="workspace-file-address-root"
              data-drop-target={dropTargetPath === "" ? "true" : undefined}
              onClick={() => navigateTo("")}
              onDragOver={(event) => handleDirectoryDragOver(event, "")}
              onDrop={(event) => void handleDirectoryDrop(event, "")}
              title={rootTitle}
              type="button"
            >
              <WorkspaceIcon />
            </button>
            <span className="workspace-file-path-separator" aria-hidden="true">›</span>
            <button
              className="workspace-file-path-segment"
              data-drop-target={dropTargetPath === "" ? "true" : undefined}
              onClick={() => navigateTo("")}
              onDragOver={(event) => handleDirectoryDragOver(event, "")}
              onDrop={(event) => void handleDirectoryDrop(event, "")}
              type="button"
            >
              根目录
            </button>
            {breadcrumb.map((part) => (
              <span className="workspace-file-path-part" key={part.path}>
                <span className="workspace-file-path-separator" aria-hidden="true">›</span>
                <button
                  className="workspace-file-path-segment"
                  data-drop-target={dropTargetPath === part.path ? "true" : undefined}
                  onClick={() => navigateTo(part.path)}
                  onDragOver={(event) => handleDirectoryDragOver(event, part.path)}
                  onDrop={(event) => void handleDirectoryDrop(event, part.path)}
                  type="button"
                >
                  {part.name}
                </button>
              </span>
            ))}
          </div>
        </nav>
      ) : null}

      {uploadProgress.active ? (
        <div className="workspace-upload-progress">
          <div className="workspace-upload-progress-meta">
            <span>正在上传 {uploadProgress.filename}</span>
            <strong>{percent}%</strong>
          </div>
          <div className="workspace-upload-progress-track"><span style={{ width: `${percent}%` }} /></div>
        </div>
      ) : null}

      {error ? (
        <p className="agent-file-panel-note is-error">
          <span>{error}</span>
          <button onClick={() => setError(null)} type="button">关闭</button>
        </p>
      ) : null}
      {notice ? (
        <p className="agent-file-panel-note is-success">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} type="button">关闭</button>
        </p>
      ) : null}
      {pendingConfirmation ? (
        <div className={`workspace-confirm-card is-${pendingConfirmation.tone}`}>
          <div>
            <strong>{pendingConfirmation.title}</strong>
            <span>{pendingConfirmation.detail}</span>
          </div>
          <div className="workspace-confirm-actions">
            <button disabled={confirmationBusy} onClick={() => setPendingConfirmation(null)} type="button">取消</button>
            <button disabled={confirmationBusy} onClick={() => void handleConfirmAction()} type="button">{pendingConfirmation.confirmLabel}</button>
          </div>
        </div>
      ) : null}
      {latestAgentRun ? renderWorkspaceAgentRun(latestAgentRun) : null}
      {loading ? <p className="agent-file-panel-note">正在读取目录...</p> : null}
      {!loading && !error && visibleItems.length === 0 ? (
        <div className="agent-file-empty">
          <strong>{viewMode === "trash" ? "回收站为空" : "这里还没有文件"}</strong>
          <span>{viewMode === "trash" ? "删除后的文件会先保留在这里。" : "拖入文件，或从顶部按钮上传/新建文件夹。"}</span>
        </div>
      ) : null}
      {!loading && visibleItems.length > 0 ? (
        viewMode === "trash" ? (
          <div className="workspace-trash-table">
            {visibleItems.map((item) => (
              <div className="workspace-trash-row" key={`${item.id}-${item.path}`}>
                <span className="workspace-trash-name">{item.name}</span>
                <span className="workspace-trash-path">{item.path}</span>
                <span>{formatSize(item.size)}</span>
                <span>{item.deleted_at ? parseApiDate(item.deleted_at).toLocaleString("zh-CN") : ""}</span>
                <div>
                  <button disabled={!item.can_restore} onClick={() => void handleRestore(item)} type="button">还原</button>
                  <button disabled={!item.can_delete} onClick={() => void handlePermanentDelete(item)} type="button">删除</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="workspace-file-list" role="list">
            {visibleItems.map((item) => {
              const isDirectory = item.type === "directory";
              const isTrashDirectory = isTrashWorkspaceItem(item);
              const fileKind = isDirectory ? "directory" : getFileKind(item.name);
              const ragStatus = getRagStatusMeta(item.rag_status);
              const canDragItem = canModifyWorkspaceItem(item);
              const isDropTarget = isDirectory && dropTargetPath === item.path;
              return (
                <div
                  className={`workspace-file-row is-${fileKind}`}
                  data-cut={clipboardItem?.action === "cut" && clipboardItem.item.path === item.path ? "true" : undefined}
                  data-drop-target={isDropTarget ? "true" : undefined}
                  data-selected={filePreview?.item.path === item.path ? "true" : undefined}
                  draggable={canDragItem}
                  key={item.path}
                  onClick={() => activateFileItem(item)}
                  onContextMenu={(event) => openFileContextMenu(event, item)}
                  onDragEnd={handleFileDragEnd}
                  onDragOver={isDirectory ? (event) => handleDirectoryDragOver(event, item.path) : undefined}
                  onDragStart={(event) => handleFileDragStart(event, item)}
                  onDrop={isDirectory ? (event) => void handleDirectoryDrop(event, item.path) : undefined}
                  onKeyDown={(event) => handleFileItemKeyDown(event, item)}
                  role="listitem"
                  tabIndex={0}
                  title={item.path}
                >
                  <span className="workspace-file-row-icon">{isTrashDirectory ? <TrashIcon /> : isDirectory ? <WorkspaceIcon /> : <NoteIcon />}</span>
                  <span className="workspace-file-row-name">{item.name}</span>
                  <span className="workspace-file-row-size">{isTrashDirectory ? "回收站" : isDirectory ? "文件夹" : formatSize(item.size)}</span>
                  {isTrashDirectory ? (
                    <span className="workspace-rag-badge is-muted">回收站</span>
                  ) : isDirectory ? (
                    <span className="workspace-rag-badge is-directory">目录</span>
                  ) : isPersonalWorkspace ? (
                    <span className="workspace-rag-badge is-muted" title="个人工作台文件不会自动进入知识库">暂存</span>
                  ) : (
                    <span className={`workspace-rag-badge is-${ragStatus.tone}`} title={ragStatus.title}>{ragStatus.label}</span>
                  )}
                </div>
              );
            })}
          </div>
        )
      ) : null}
      {contextMenu ? (
        <div
          className="workspace-file-context-menu"
          onClick={(event) => event.stopPropagation()}
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button onClick={() => runContextAction(() => activateFileItem(contextMenu.item))} type="button">{isTrashWorkspaceItem(contextMenu.item) ? <TrashIcon /> : contextMenu.item.type === "directory" ? <WorkspaceIcon /> : <NoteIcon />}{isTrashWorkspaceItem(contextMenu.item) ? "打开回收站" : contextMenu.item.type === "directory" ? "打开" : "预览"}</button>
          <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCut(contextMenu.item))} type="button"><MoveIcon />剪切</button>
          <button disabled={!canCopyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCopy(contextMenu.item))} type="button"><CopyIcon />复制</button>
          {contextMenu.item.type === "directory" ? (
            <button disabled={!canPasteInto(contextMenu.item.path)} onClick={() => runContextAction(() => void handlePaste(contextMenu.item.path))} type="button"><CopyIcon />粘贴到此处</button>
          ) : null}
          <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => void handleRename(contextMenu.item))} type="button"><EditIcon />重命名</button>
          <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => void handleDelete(contextMenu.item))} type="button"><TrashIcon />删除</button>
          <button disabled={loading} onClick={() => runContextAction(() => void refresh())} type="button"><RefreshIcon />刷新</button>
          <button disabled={isTrashWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => void handleCreateFolder(contextMenu.item.type === "directory" ? contextMenu.item.path : currentPath))} type="button"><WorkspaceIcon />新建文件夹</button>
          {contextMenu.item.type !== "directory" ? (
            <button onClick={() => runContextAction(() => void onReferenceFile?.(contextMenu.item))} type="button"><NoteIcon />引用文件</button>
          ) : null}
          {contextMenu.item.type !== "directory" ? (
            <button onClick={() => runContextAction(() => void openFilePreview(contextMenu.item))} type="button"><NoteIcon />详细信息</button>
          ) : null}
        </div>
      ) : null}
      {dragOver ? <div className="workspace-drop-hint">松开后上传到当前文件夹</div> : null}
    </section>
    {filePreview ? (
      <aside className={`workspace-file-preview-sidecar is-${filePreview.kind} ${previewResizing ? "is-resizing" : ""}`} aria-label="文件预览">
        <div
          aria-label="调整预览面板宽度"
          aria-orientation="vertical"
          className="workspace-file-preview-resize-handle"
          onMouseDown={handlePreviewResizeStart}
          role="separator"
          title="拖动调整预览面板宽度"
        />
        <header className="workspace-file-preview-sidecar-header">
          <div>
            <strong>预览</strong>
            <span>{filePreview.item.name}</span>
          </div>
          <button aria-label="关闭预览" className="workspace-file-action" onClick={closeFilePreview} title="关闭预览" type="button"><XmarkIcon /></button>
        </header>
        <div className="workspace-file-preview-stage">
          {filePreview.status === "loading" ? <span>正在加载预览...</span> : null}
          {filePreview.status === "failed" ? <span>{filePreview.error || "文件预览失败"}</span> : null}
          {filePreview.status === "ready" && filePreview.kind === "image" && filePreview.objectUrl ? (
            <img alt={filePreview.item.name} src={filePreview.objectUrl} />
          ) : null}
          {filePreview.status === "ready" && filePreview.kind === "pdf" && filePreview.objectUrl ? (
            <iframe src={filePreview.objectUrl} title={filePreview.item.name} />
          ) : null}
          {filePreview.status === "ready" && filePreview.text != null ? (
            <pre>{filePreview.text}</pre>
          ) : null}
          {filePreview.status === "ready" && !["image", "pdf"].includes(filePreview.kind) && filePreview.text == null ? (
            <span>当前格式暂不支持内嵌预览。</span>
          ) : null}
        </div>
        <section className="workspace-file-preview-details" aria-label="详细信息">
          <h3>详细信息</h3>
          <dl>
            <div><dt>类型</dt><dd>{filePreview.kind === "image" ? "图片文件" : filePreview.kind === "pdf" ? "PDF 文件" : filePreview.kind === "code" ? "文本/代码文件" : "文件"}</dd></div>
            <div><dt>大小</dt><dd>{formatSize(filePreview.item.size)}</dd></div>
            <div><dt>上传人</dt><dd>{filePreview.item.uploader_name || (filePreview.item.uploaded_by ? `用户 #${filePreview.item.uploaded_by}` : "-")}</dd></div>
            <div><dt>位置</dt><dd title={filePreview.item.path}>{filePreview.item.path}</dd></div>
            <div><dt>修改日期</dt><dd>{filePreview.item.updated_at ? parseApiDate(filePreview.item.updated_at).toLocaleString("zh-CN") : "-"}</dd></div>
            <div><dt>入库状态</dt><dd>{getRagStatusMeta(filePreview.item.rag_status).label}</dd></div>
          </dl>
        </section>
      </aside>
    ) : null}
    {knowledgeGraphOpen && !filePreview ? (
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
                            {nativeGraphLoadingSlug === card.id ? "读取..." : "原生"}
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
                        {nativeGraphLoadingSlug === selectedGraphNode.id ? "读取..." : "读取原生上下文"}
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
                  <h3>GBrain 原生上下文</h3>
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
    ) : null}
    {knowledgeGraphCanvasOpen && knowledgeGraph ? (
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
                        <title>{`${nodeTitleById.get(edge.from) || edge.from} -> ${edge.relation_type} -> ${nodeTitleById.get(edge.to) || edge.to}`}</title>
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
                        <text className="workspace-knowledge-map-node-type" textAnchor="middle" y="13">{node.entity_type || "entity"}</text>
                        <title>{`${node.title} · ${node.entity_type || "entity"} · ${degree} 条关系`}</title>
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
                    <span>{[selectedGraphNode.entity_type, selectedGraphNode.source_file || selectedGraphNode.file].filter(Boolean).join(" · ") || "未标来源"}</span>
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
                          <span>{edge.relation_type}</span>
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
    ) : null}
    </div>
  );
}
