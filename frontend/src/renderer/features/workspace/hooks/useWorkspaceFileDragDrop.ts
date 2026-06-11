import { useState, type DragEvent } from "react";

import type { WorkspaceFileItemResponse } from "../../../shared/api/types";
import {
  hasWorkspaceDrag,
  isTrashPath,
  WORKSPACE_DRAG_MIME,
} from "../workspaceFilePanelUtils";

export function useWorkspaceFileDragDrop({
  currentPath,
  canModifyWorkspaceItem,
  canMoveItemTo,
  executeMove,
  handleUpload,
  setDragOver,
}: {
  currentPath: string;
  canModifyWorkspaceItem: (item: WorkspaceFileItemResponse) => boolean;
  canMoveItemTo: (item: WorkspaceFileItemResponse, targetDirectory: string) => boolean;
  executeMove: (item: WorkspaceFileItemResponse, targetDirectory: string) => Promise<void>;
  handleUpload: (fileList: FileList | File[] | null, directory?: string) => Promise<void>;
  setDragOver: (value: boolean) => void;
}) {
  const [draggedItem, setDraggedItem] = useState<WorkspaceFileItemResponse | null>(null);
  const [dropTargetPath, setDropTargetPath] = useState<string | null>(null);

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

  return {
    draggedItem,
    dropTargetPath,
    setDropTargetPath,
    handleFileDragStart,
    handleFileDragEnd,
    handleDirectoryDragOver,
    handleDirectoryDrop,
    handleDrop,
  };
}
