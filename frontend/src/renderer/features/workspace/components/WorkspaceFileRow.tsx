import type { DragEvent, KeyboardEvent, MouseEvent } from "react";

import type { WorkspaceFileItemResponse } from "../../../shared/api/types";
import {
  formatSize,
  getFileKind,
  getRagStatusMeta,
  isTrashWorkspaceItem,
} from "../workspaceFilePanelUtils";
import {
  NoteIcon,
  TrashIcon,
  WorkspaceIcon,
} from "../../../shared/icons/LineIcons";

type WorkspaceFileRowProps = {
  item: WorkspaceFileItemResponse;
  selectedPath?: string;
  cutPath?: string;
  dropTargetPath: string | null;
  canDrag: boolean;
  isPersonalWorkspace: boolean;
  canShowKnowledgeIngest: boolean;
  onActivate: (item: WorkspaceFileItemResponse) => void;
  onContextMenu: (event: MouseEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) => void;
  onDragEnd: () => void;
  onDragOverDirectory: (event: DragEvent<HTMLDivElement>, path: string) => void;
  onDragStart: (event: DragEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) => void;
  onDropDirectory: (event: DragEvent<HTMLDivElement>, path: string) => void | Promise<void>;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>, item: WorkspaceFileItemResponse) => void;
  onRetryKnowledge: (item: WorkspaceFileItemResponse) => void;
  onShowMeetingDetail: (item: WorkspaceFileItemResponse) => void;
};

export function WorkspaceFileRow({
  item,
  selectedPath,
  cutPath,
  dropTargetPath,
  canDrag,
  isPersonalWorkspace,
  canShowKnowledgeIngest,
  onActivate,
  onContextMenu,
  onDragEnd,
  onDragOverDirectory,
  onDragStart,
  onDropDirectory,
  onKeyDown,
  onRetryKnowledge,
  onShowMeetingDetail,
}: WorkspaceFileRowProps) {
  const isDirectory = item.type === "directory";
  const isTrashDirectory = isTrashWorkspaceItem(item);
  const fileKind = isDirectory ? "directory" : getFileKind(item.name);
  const ragStatus = getRagStatusMeta(item.rag_status);
  const isDropTarget = isDirectory && dropTargetPath === item.path;

  return (
    <div
      className={`workspace-file-row is-${fileKind}`}
      data-cut={cutPath === item.path ? "true" : undefined}
      data-drop-target={isDropTarget ? "true" : undefined}
      data-selected={selectedPath === item.path ? "true" : undefined}
      draggable={canDrag}
      onClick={() => onActivate(item)}
      onContextMenu={(event) => onContextMenu(event, item)}
      onDragEnd={onDragEnd}
      onDragOver={isDirectory ? (event) => onDragOverDirectory(event, item.path) : undefined}
      onDragStart={(event) => onDragStart(event, item)}
      onDrop={isDirectory ? (event) => void onDropDirectory(event, item.path) : undefined}
      onKeyDown={(event) => onKeyDown(event, item)}
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
        <span className={`workspace-rag-badge is-${ragStatus.tone}`} title={ragStatus.title}>
          {ragStatus.label}
          {item.rag_status === "failed" && canShowKnowledgeIngest ? (
            <button
              className="workspace-rag-retry"
              onClick={(event) => {
                event.stopPropagation();
                onRetryKnowledge(item);
              }}
              title="重新处理此文件"
              type="button"
            >重试</button>
          ) : null}
          {item.rag_status === "partial" || item.rag_status === "pending_transcription" ? (
            <button
              className="workspace-rag-retry"
              onClick={(event) => {
                event.stopPropagation();
                onShowMeetingDetail(item);
              }}
              title="查看详情"
              type="button"
            >详情</button>
          ) : null}
        </span>
      )}
    </div>
  );
}
