import type { DragEvent } from "react";

import type { WorkspaceFileItemResponse } from "../../shared/api/types";

export const MEETING_ROOT_PATH = "20-会议与沟通";
export const MEETING_WORKFLOW_DIRS = [
  "01-原始资料",
  "02-转录文本",
  "03-辅助总结",
  "04-会议纪要",
  "05-行动项",
];

export const TRASH_DIRECTORY = ".trash";
export const WORKSPACE_DRAG_MIME = "application/x-project-r-workspace-file";
export const PREVIEW_DEFAULT_WIDTH = 320;

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
const PREVIEW_WIDTH_KEY = "project-r:workspace-file-preview-width";
const PREVIEW_MIN_WIDTH = 240;
const PREVIEW_MAX_WIDTH = 520;
const FILE_LIST_MIN_WIDTH = 300;
const FILE_PANEL_GAP = 10;

export function getPreviewMaxWidth(containerWidth?: number) {
  if (!Number.isFinite(containerWidth)) return PREVIEW_MAX_WIDTH;
  return Math.max(PREVIEW_MIN_WIDTH, Math.min(PREVIEW_MAX_WIDTH, Math.round((containerWidth ?? 0) - FILE_LIST_MIN_WIDTH - FILE_PANEL_GAP)));
}

export function clampPreviewWidth(value: number, containerWidth?: number) {
  return Math.min(getPreviewMaxWidth(containerWidth), Math.max(PREVIEW_MIN_WIDTH, Math.round(value)));
}

export function readPreviewWidth() {
  try {
    const stored = Number(localStorage.getItem(PREVIEW_WIDTH_KEY));
    return Number.isFinite(stored) ? clampPreviewWidth(stored) : PREVIEW_DEFAULT_WIDTH;
  } catch {
    // localStorage may be unavailable in restricted shells.
    return PREVIEW_DEFAULT_WIDTH;
  }
}

export function writePreviewWidth(width: number) {
  try {
    localStorage.setItem(PREVIEW_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

export function formatSize(size: number | null) {
  if (size === null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function getRagStatusMeta(status: string | null | undefined) {
  if (status === "synced") return { label: "已同步", tone: "indexed", title: "已同步到当前工作区知识库" };
  if (status === "indexed") return { label: "已入库", tone: "indexed", title: "已同步到当前工作区知识库" };
  if (status === "failed") return { label: "索引失败", tone: "failed", title: "索引失败，右键文件后可重新处理或联系管理员" };
  if (status === "new" || status === "pending") return { label: "待处理", tone: "pending", title: "已上传，等待用户触发录入" };
  if (status === "source_changed") return { label: "需重录", tone: "processing", title: "源文件已变更，需要用户显式重新录入" };
  if (status === "needs_repreprocess") return { label: "需重录", tone: "processing", title: "预处理产物已过期，需要重新录入" };
  if (status === "source_deleted") return { label: "源已删", tone: "muted", title: "源文件已删除，已同步知识不会自动删除" };
  if (status === "sync_pending") return { label: "待同步", tone: "processing", title: "已生成 GBrain-ready 文件，等待 GBrain 同步" };
  if (status === "gbrain_ready") return { label: "待同步", tone: "processing", title: "已生成 GBrain-ready 文件，等待同步" };
  if (status === "pending_review") return { label: "待审核", tone: "pending", title: "已提炼，等待审核后进入知识库" };
  if (status === "pending_capability") return { label: "待能力", tone: "processing", title: "当前文件类型等待提炼能力补齐" };
  if (status === "pending_extractor_capability") return { label: "待能力", tone: "processing", title: "当前文件类型等待提炼能力补齐" };
  if (status === "pending_transcription") return { label: "待转写", tone: "processing", title: "音视频文件等待转写处理" };
  if (status === "ignored") return { label: "已忽略", tone: "muted", title: "该文件已被用户忽略，不参与默认录入" };
  if (status === "skipped") return { label: "暂不入库", tone: "muted", title: "当前文件暂不进入知识库" };
  if (status === "skipped_superseded_version") return { label: "已取代", tone: "muted", title: "旧版本，已有更新版本录入" };
  if (status === "needs_reingest") return { label: "需重录", tone: "processing", title: "会议已重跑，GBrain 知识需重新录入" };
  if (status === "not_ingested") return { label: "未入库", tone: "pending", title: "会议工作流输出已生成，但尚未录入 GBrain" };
  if (status === "partial") return { label: "部分完成", tone: "processing", title: "转录或纪要基于部分成功片段生成，需要人工复核" };
  return { label: "未入库", tone: "empty", title: "尚未录入当前工作区知识库" };
}

export function knowledgeStoreLabel(workspaceKind: string) {
  if (workspaceKind === "customer") return "CRM 知识库";
  if (workspaceKind === "project") return "项目知识库";
  return "工作区知识库";
}

export function isSystemWorkspaceItem(item: WorkspaceFileItemResponse) {
  if (item.type !== "directory") return false;
  return item.path.split("/").some((part) => SYSTEM_WORKSPACE_DIRECTORIES.has(part));
}

export function filterSystemWorkspaceItems(items: WorkspaceFileItemResponse[]): WorkspaceFileItemResponse[] {
  return items
    .filter((item) => !isSystemWorkspaceItem(item))
    .map((item) => item.type === "directory" ? { ...item, children: filterSystemWorkspaceItems(item.children ?? []) } : item);
}

export function isProtectedWorkspaceDirectory(item: WorkspaceFileItemResponse, workspaceKind: string) {
  return item.type === "directory" && !item.path.includes("/") && (
    item.path === TRASH_DIRECTORY || (workspaceKind !== "user" && PROTECTED_WORKSPACE_ROOT_DIRECTORIES.has(item.path))
  );
}

export function isTrashWorkspaceItem(item: WorkspaceFileItemResponse) {
  return item.type === "directory" && item.path === TRASH_DIRECTORY;
}

export function isTrashPath(path: string) {
  return path === TRASH_DIRECTORY || path.startsWith(`${TRASH_DIRECTORY}/`);
}

export function getParentPath(path: string) {
  const parts = path.split("/").filter(Boolean);
  return parts.slice(0, -1).join("/");
}

export function isDirectoryInside(sourcePath: string, targetPath: string) {
  return targetPath === sourcePath || targetPath.startsWith(`${sourcePath}/`);
}

export function hasExternalFiles(event: DragEvent<HTMLElement | HTMLDivElement>) {
  return Array.from(event.dataTransfer.types).includes("Files");
}

export function hasWorkspaceDrag(event: DragEvent<HTMLElement | HTMLDivElement>) {
  return Array.from(event.dataTransfer.types).includes(WORKSPACE_DRAG_MIME);
}

export function findDirectory(items: WorkspaceFileItemResponse[], path: string): WorkspaceFileItemResponse | null {
  for (const item of items) {
    if (item.type === "directory" && item.path === path) return item;
    const child = findDirectory(item.children ?? [], path);
    if (child) return child;
  }
  return null;
}

export function getItemsAtPath(items: WorkspaceFileItemResponse[], path: string) {
  if (!path) return items;
  return findDirectory(items, path)?.children ?? [];
}

export function makeBreadcrumb(path: string) {
  if (!path) return [];
  const parts = path.split("/");
  return parts.map((name, index) => ({
    name,
    path: parts.slice(0, index + 1).join("/"),
  }));
}

export function getFileKind(name: string) {
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

export function countPendingIngestFiles(items: WorkspaceFileItemResponse[]): number {
  let count = 0;
  for (const item of items) {
    if (item.type === "directory") {
      count += countPendingIngestFiles(item.children ?? []);
      continue;
    }
    const status = item.rag_status ?? "not_indexed";
    if (!["indexed", "synced", "skipped", "source_deleted", "ignored"].includes(status)) count += 1;
  }
  return count;
}
