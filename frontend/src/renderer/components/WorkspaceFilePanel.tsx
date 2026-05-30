import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";

import {
  clearWorkspaceTrash,
  createWorkspaceFolder,
  deleteWorkspaceFile,
  deleteWorkspaceFolder,
  enqueueWorkspaceKnowledgeIngest,
  getWorkspaceKnowledgeIngestJob,
  permanentlyDeleteWorkspaceFile,
  moveWorkspacePath,
  renameWorkspacePath,
  restoreWorkspaceFile,
  listWorkspaceFiles,
  uploadWorkspaceFiles,
} from "../api/workspaces";
import type { ApiClientOptions } from "../api/client";
import type { WorkspaceFileItemResponse } from "../api/types";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  EditIcon,
  MoreIcon,
  MoveIcon,
  NoteIcon,
  PlusIcon,
  RefreshIcon,
  TrashIcon,
  WorkspaceIcon,
} from "./LineIcons";

export type WorkspaceFilePanelProps = {
  apiOptions: ApiClientOptions;
  workspaceId: number | null;
  workspaceName?: string;
};

function formatSize(size: number | null) {
  if (size === null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatRagStatus(status: string) {
  if (status === "indexed") return "已入库";
  if (status === "not_indexed") return "未入库";
  if (status === "pending_review") return "待审核";
  if (status === "pending_extractor_capability") return "待能力补齐";
  if (status === "pending_transcription") return "待转写";
  if (status === "failed") return "索引失败";
  if (status === "skipped") return "暂不入库";
  return "待录入";
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

export function WorkspaceFilePanel({ apiOptions, workspaceId, workspaceName }: WorkspaceFilePanelProps) {
  const [items, setItems] = useState<WorkspaceFileItemResponse[]>([]);
  const [currentPath, setCurrentPath] = useState("");
  const [history, setHistory] = useState<string[]>([""]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"files" | "trash">("files");
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshingKnowledge, setRefreshingKnowledge] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ active: false, current: 0, total: 0, filename: "" });
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const visibleItems = useMemo(() => viewMode === "trash" ? items : getItemsAtPath(items, currentPath), [currentPath, items, viewMode]);
  const breadcrumb = useMemo(() => makeBreadcrumb(currentPath), [currentPath]);
  const pendingIngestCount = useMemo(() => countPendingIngestFiles(items), [items]);

  function navigateTo(path: string) {
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
        if (viewMode === "files" && currentPath && !findDirectory(response.items, currentPath)) {
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

  async function handleUpload(fileList: FileList | File[] | null, directory = currentPath) {
    const files = Array.from(fileList ?? []);
    if (!workspaceId || files.length === 0) return;
    setError(null);
    setNotice(null);
    setUploadProgress({ active: true, current: 0, total: files.length, filename: files[0]?.name ?? "" });
    try {
      await uploadWorkspaceFiles(apiOptions, workspaceId, directory, files);
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
    const name = window.prompt("新建文件夹名称");
    if (!name?.trim()) return;
    try {
      await createWorkspaceFolder(apiOptions, workspaceId, { parent_path: parentPath, name });
      await refresh();
    } catch (createError: unknown) {
      setError(createError instanceof Error ? createError.message : "新建文件夹失败");
    }
  }

  async function handleRename(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    const name = window.prompt("重命名", item.name);
    if (!name?.trim() || name.trim() === item.name) return;
    try {
      await renameWorkspacePath(apiOptions, workspaceId, { path: item.path, new_name: name.trim() });
      await refresh();
    } catch (renameError: unknown) {
      setError(renameError instanceof Error ? renameError.message : "重命名失败");
    }
  }

  async function handleMove(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    const target = window.prompt("移动到文件夹路径，留空表示根目录", currentPath);
    if (target === null) return;
    try {
      await moveWorkspacePath(apiOptions, workspaceId, { path: item.path, target_directory: target.trim(), conflict_strategy: "keep_both" });
      await refresh();
    } catch (moveError: unknown) {
      setError(moveError instanceof Error ? moveError.message : "移动失败");
    }
  }

  async function handleDelete(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    if (!item.can_delete && item.type !== "directory") {
      setError("只能删除自己上传的文件");
      return;
    }
    const confirmed = window.confirm(item.type === "directory" ? `删除空文件夹「${item.name}」？` : `将「${item.name}」移入回收区？`);
    if (!confirmed) return;
    try {
      if (item.type === "directory") {
        await deleteWorkspaceFolder(apiOptions, workspaceId, item.path);
        if (currentPath.startsWith(`${item.path}/`)) navigateTo("");
      } else {
        await deleteWorkspaceFile(apiOptions, workspaceId, item.path);
      }
      await refresh();
    } catch (deleteError: unknown) {
      setError(deleteError instanceof Error ? deleteError.message : "删除失败");
    }
  }

  async function handleRestore(item: WorkspaceFileItemResponse) {
    if (!workspaceId || !item.id) return;
    try {
      await restoreWorkspaceFile(apiOptions, workspaceId, item.id);
      await refresh();
    } catch (restoreError: unknown) {
      setError(restoreError instanceof Error ? restoreError.message : "恢复失败");
    }
  }

  async function handlePermanentDelete(item: WorkspaceFileItemResponse) {
    if (!workspaceId || !item.id) return;
    if (!window.confirm(`永久删除「${item.name}」？此操作不可恢复。`)) return;
    try {
      await permanentlyDeleteWorkspaceFile(apiOptions, workspaceId, item.id);
      await refresh();
    } catch (deleteError: unknown) {
      setError(deleteError instanceof Error ? deleteError.message : "永久删除失败");
    }
  }

  async function handleRefreshKnowledge() {
    if (!workspaceId) return;
    setRefreshingKnowledge(true);
    setError(null);
    setNotice(null);
    try {
      const queued = await enqueueWorkspaceKnowledgeIngest(apiOptions, workspaceId);
      setNotice(`项目知识库录入已进入后台队列：任务 #${queued.id}。`);
      let job = queued;
      for (let attempt = 0; attempt < 120 && ["queued", "running"].includes(job.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        job = await getWorkspaceKnowledgeIngestJob(apiOptions, workspaceId, queued.id);
      }
      if (["queued", "running"].includes(job.status)) {
        setNotice(`项目知识库录入仍在后台执行：任务 #${queued.id}，完成后会通知你。`);
        return;
      }
      const result = job.result;
      if (!result.ok) {
        const detail = job.error_message || result.gbrain_error || result.gbrain_status || "项目资料已处理，但 GBrain source 尚未完成同步";
        setError(`录入未完成：${detail}`);
      } else {
        const parts = [
          `已入库 ${result.indexed_files ?? 0} 个`,
          `待能力补齐 ${result.pending_extractor_capability_files ?? 0} 个`,
          `待转写 ${result.pending_transcription_files ?? 0} 个`,
        ];
        if ((result.failed_files ?? 0) > 0) parts.push(`失败 ${result.failed_files} 个`);
        setNotice(`项目知识库录入完成：${parts.join("，")}。`);
      }
      await refresh();
    } catch (refreshError: unknown) {
      setError(refreshError instanceof Error ? refreshError.message : "录入项目知识库失败");
    } finally {
      setRefreshingKnowledge(false);
    }
  }

  async function handleClearTrash() {
    if (!workspaceId || !window.confirm("清空回收区？此操作不可恢复。")) return;
    try {
      await clearWorkspaceTrash(apiOptions, workspaceId);
      await refresh();
    } catch (clearError: unknown) {
      setError(clearError instanceof Error ? clearError.message : "清空回收区失败");
    }
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragOver(false);
    void handleUpload(Array.from(event.dataTransfer.files), currentPath);
  }

  const percent = uploadProgress.total > 0 ? Math.round((uploadProgress.current / uploadProgress.total) * 100) : 0;

  return (
    <section
      className={`agent-file-panel ${dragOver ? "is-drag-over" : ""}`}
      onDragLeave={() => setDragOver(false)}
      onDragOver={(event) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDrop={handleDrop}
    >
      <header className="agent-file-panel-header">
        <span className="agent-file-panel-icon"><WorkspaceIcon /></span>
        <div>
          <h2>{workspaceName ?? "当前工作区"}</h2>
          <p>{viewMode === "trash" ? "回收区" : "项目参考文件"}</p>
        </div>
        <div className="agent-file-panel-actions">
          <input className="hidden-file-input" multiple onChange={(event) => void handleUpload(event.target.files)} ref={fileInputRef} type="file" />
          <button className="workspace-file-action" disabled={historyIndex <= 0 || viewMode === "trash"} onClick={goBack} title="返回" type="button"><ChevronLeftIcon /></button>
          <button className="workspace-file-action" disabled={historyIndex >= history.length - 1 || viewMode === "trash"} onClick={goForward} title="前进" type="button"><ChevronRightIcon /></button>
          <button className="workspace-file-action" disabled={!currentPath || viewMode === "trash"} onClick={goUp} title="向上" type="button"><WorkspaceIcon /></button>
          <button className="workspace-file-action" disabled={!currentPath || viewMode === "trash"} onClick={() => navigateTo("")} title="根目录" type="button"><NoteIcon /></button>
          <span className="workspace-file-more-wrap">
            <button className="workspace-file-action" onClick={() => setMoreOpen((value) => !value)} title="更多" type="button"><MoreIcon /></button>
            {moreOpen ? (
              <div className="workspace-file-more-menu">
                <button onClick={() => { setMoreOpen(false); fileInputRef.current?.click(); }} type="button"><PlusIcon />上传文件</button>
                <button onClick={() => { setMoreOpen(false); void handleCreateFolder(); }} type="button"><WorkspaceIcon />新建文件夹</button>
                <button disabled={viewMode === "trash" || refreshingKnowledge || pendingIngestCount === 0} onClick={() => { setMoreOpen(false); void handleRefreshKnowledge(); }} type="button"><RefreshIcon />{refreshingKnowledge ? "正在录入..." : `一键录入项目知识库${pendingIngestCount > 0 ? ` (${pendingIngestCount})` : ""}`}</button>
                <button onClick={() => { setMoreOpen(false); setViewMode(viewMode === "trash" ? "files" : "trash"); navigateTo(""); }} type="button"><TrashIcon />{viewMode === "trash" ? "项目文件" : "回收区"}</button>
                {viewMode === "trash" ? <button onClick={() => { setMoreOpen(false); void handleClearTrash(); }} type="button"><TrashIcon />清空回收区</button> : null}
              </div>
            ) : null}
          </span>
        </div>
      </header>

      {viewMode === "files" ? (
        <nav className="workspace-file-breadcrumb" aria-label="项目文件路径">
          <button onClick={() => navigateTo("")} type="button">根目录</button>
          {breadcrumb.map((part) => <button key={part.path} onClick={() => navigateTo(part.path)} type="button">{part.name}</button>)}
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
      {loading ? <p className="agent-file-panel-note">正在读取目录...</p> : null}
      {!loading && !error && visibleItems.length === 0 ? (
        <div className="agent-file-empty">
          <strong>{viewMode === "trash" ? "回收区为空" : "这里还没有文件"}</strong>
          <span>{viewMode === "trash" ? "删除后的文件会先保留在这里。" : "拖入文件，或从更多菜单上传/新建文件夹。"}</span>
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
                <span>{item.deleted_at ? new Date(item.deleted_at).toLocaleString("zh-CN") : ""}</span>
                <div>
                  <button disabled={!item.can_restore} onClick={() => void handleRestore(item)} type="button">还原</button>
                  <button disabled={!item.can_delete} onClick={() => void handlePermanentDelete(item)} type="button">删除</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="workspace-file-grid">
            {visibleItems.map((item) => {
              const isDirectory = item.type === "directory";
              const fileKind = isDirectory ? "directory" : getFileKind(item.name);
              return (
                <div className={`workspace-file-tile is-${fileKind}`} key={item.path} title={item.path}>
                  <button className="workspace-file-tile-main" onDoubleClick={() => isDirectory ? navigateTo(item.path) : undefined} onClick={() => isDirectory ? navigateTo(item.path) : undefined} type="button">
                    <span className="workspace-file-tile-icon">{isDirectory ? <WorkspaceIcon /> : <NoteIcon />}</span>
                    <span className="workspace-file-tile-name">{item.name}</span>
                    <small>{isDirectory ? "文件夹" : formatSize(item.size)}</small>
                    {!isDirectory && item.rag_status ? <small>{formatRagStatus(item.rag_status)}</small> : null}
                  </button>
                  {(isDirectory || item.can_delete) ? (
                    <div className="workspace-file-tile-toolbar">
                      <button onClick={() => void handleRename(item)} title="重命名" type="button"><EditIcon /></button>
                      <button onClick={() => void handleMove(item)} title="移动到" type="button"><MoveIcon /></button>
                      <button onClick={() => void handleDelete(item)} title="删除" type="button"><TrashIcon /></button>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )
      ) : null}
      {dragOver ? <div className="workspace-drop-hint">松开后上传到当前文件夹</div> : null}
    </section>
  );
}
