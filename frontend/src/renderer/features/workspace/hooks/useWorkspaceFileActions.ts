import { useState, type Dispatch, type RefObject, type SetStateAction } from "react";

import type { WorkspaceConfirmation, WorkspaceTextPrompt } from "../components/WorkspaceDialogs";
import type { WorkspaceClipboardItem } from "../components/workspaceFilePanelTypes";
import {
  clearWorkspaceTrash,
  copyWorkspacePath,
  createWorkspaceFolder,
  deleteWorkspaceFile,
  deleteWorkspaceFolder,
  enqueueWorkspaceKnowledgeIngest,
  fetchWorkspaceFileBlob,
  getWorkspaceKnowledgeIngestJob,
  moveWorkspacePath,
  permanentlyDeleteWorkspaceFile,
  renameWorkspacePath,
  restoreWorkspaceFile,
  uploadWorkspaceFiles,
} from "../api";
import {
  countPendingIngestFiles,
  getParentPath,
  isDirectoryInside,
  isProtectedWorkspaceDirectory,
  isTrashPath,
  isTrashWorkspaceItem,
  knowledgeStoreLabel,
} from "../workspaceFilePanelUtils";
import type { ApiClientOptions } from "../../../shared/api/client";
import type { AgentRunResponse, WorkspaceFileItemResponse } from "../../../shared/api/types";

export type WorkspaceUploadProgressState = {
  active: boolean;
  current: number;
  total: number;
  filename: string;
};

export function useWorkspaceFileActions({
  activePreviewPath,
  apiOptions,
  closeFilePreview,
  currentPath,
  fileInputRef,
  navigateTo,
  pendingIngestCount,
  refresh,
  setError,
  setLatestAgentRun,
  setNotice,
  setPendingConfirmation,
  setRefreshingKnowledge,
  workspaceId,
  workspaceKind,
}: {
  activePreviewPath?: string;
  apiOptions: ApiClientOptions;
  closeFilePreview: () => void;
  currentPath: string;
  fileInputRef: RefObject<HTMLInputElement | null>;
  navigateTo: (path: string) => void;
  pendingIngestCount: number;
  refresh: () => Promise<void>;
  setError: (message: string | null) => void;
  setLatestAgentRun: Dispatch<SetStateAction<AgentRunResponse | null>>;
  setNotice: (message: string | null) => void;
  setPendingConfirmation: Dispatch<SetStateAction<WorkspaceConfirmation | null>>;
  setRefreshingKnowledge: (refreshing: boolean) => void;
  workspaceId: number | null;
  workspaceKind: string;
}) {
  const [clipboardItem, setClipboardItem] = useState<WorkspaceClipboardItem | null>(null);
  const [textPrompt, setTextPrompt] = useState<WorkspaceTextPrompt | null>(null);
  const [textPromptValue, setTextPromptValue] = useState("");
  const [textPromptBusy, setTextPromptBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<WorkspaceUploadProgressState>({ active: false, current: 0, total: 0, filename: "" });

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

  function openTextPrompt(prompt: WorkspaceTextPrompt) {
    setTextPrompt(prompt);
    setTextPromptValue(prompt.initialValue);
    setTextPromptBusy(false);
  }

  async function handleTextPromptSubmit() {
    if (!textPrompt || textPromptBusy) return;
    const value = textPromptValue.trim();
    if (!value) return;
    setTextPromptBusy(true);
    setError(null);
    try {
      await textPrompt.onConfirm(value);
      setTextPrompt(null);
      setTextPromptValue("");
    } catch (promptError: unknown) {
      setError(promptError instanceof Error ? promptError.message : "操作失败");
    } finally {
      setTextPromptBusy(false);
    }
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

  function handleCreateFolder(parentPath = currentPath) {
    if (!workspaceId) return;
    if (isTrashPath(parentPath)) {
      setError("回收站不能新建文件夹");
      return;
    }
    openTextPrompt({
      title: "新建文件夹",
      label: parentPath ? `位置：${parentPath}` : "位置：根目录",
      initialValue: "",
      confirmLabel: "新建",
      onConfirm: async (name) => {
        const response = await createWorkspaceFolder(apiOptions, workspaceId, { parent_path: parentPath, name });
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
  }

  function handleRename(item: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    if (!canModifyWorkspaceItem(item)) {
      setError("只有上传人或管理员可以修改该文件");
      return;
    }
    openTextPrompt({
      title: "重命名",
      label: item.path,
      initialValue: item.name,
      confirmLabel: "保存",
      onConfirm: async (name) => {
        if (name === item.name) return;
        const response = await renameWorkspacePath(apiOptions, workspaceId, { path: item.path, new_name: name });
        if (response.agent_run) setLatestAgentRun(response.agent_run);
        await refresh();
      },
    });
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
      if (activePreviewPath === item.path) closeFilePreview();
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

  async function runKnowledgeIngest(path: string, recursive: boolean) {
    if (!workspaceId) return;
    const storeLabel = knowledgeStoreLabel(workspaceKind);
    setRefreshingKnowledge(true);
    setError(null);
    setNotice(null);
    try {
      const queued = await enqueueWorkspaceKnowledgeIngest(apiOptions, workspaceId, { path, recursive });
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

  function handleRefreshKnowledge(path = currentPath, recursive = true, item?: WorkspaceFileItemResponse) {
    if (!workspaceId) return;
    const targetType = item?.type === "file" ? "file" : "directory";
    const pendingCount = item ? countPendingIngestFiles([item]) : pendingIngestCount;
    const pathLabel = path ? `「${path}」` : "当前文件夹";
    if (recursive || targetType === "directory") {
      setPendingConfirmation({
        title: targetType === "file" ? "录入此文件" : "递归录入当前文件夹",
        detail: [
          `路径：${pathLabel}`,
          targetType === "file" ? "范围：仅此文件" : `范围：递归包含子文件夹，当前可处理文件约 ${pendingCount} 个`,
          "可能调用高成本模型、转写或视觉提炼能力；不支持的文件会标记为待能力补齐。",
        ].join("；"),
        confirmLabel: targetType === "file" ? "录入此文件" : "确认录入",
        tone: "warning",
        onConfirm: () => runKnowledgeIngest(path, targetType === "file" ? false : recursive),
      });
      return;
    }
    void runKnowledgeIngest(path, false);
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

  async function downloadWorkspaceFile(item: WorkspaceFileItemResponse) {
    if (!workspaceId || item.type === "directory") return;
    setError(null);
    try {
      const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = item.name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setNotice(`已开始下载：${item.name}`);
    } catch (downloadError: unknown) {
      setError(downloadError instanceof Error ? downloadError.message : "文件下载失败");
    }
  }

  return {
    canCopyWorkspaceItem,
    canModifyWorkspaceItem,
    canMoveItemTo,
    canPasteInto,
    clipboardItem,
    downloadWorkspaceFile,
    executeMove,
    handleClearTrash,
    handleCopy,
    handleCreateFolder,
    handleCut,
    handleDelete,
    handlePaste,
    handlePermanentDelete,
    handleRefreshKnowledge,
    handleRename,
    handleRestore,
    handleTextPromptSubmit,
    handleUpload,
    setTextPrompt,
    setTextPromptValue,
    textPrompt,
    textPromptBusy,
    textPromptValue,
    uploadProgress,
  };
}
