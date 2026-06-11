import type { DragEvent } from "react";

import {
  ArrowUpIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  WorkspaceIcon,
} from "../../../shared/icons/LineIcons";

type WorkspaceBreadcrumbPart = {
  name: string;
  path: string;
};

type WorkspaceFileBreadcrumbProps = {
  viewMode: "files" | "trash";
  isPersonalWorkspace: boolean;
  rootTitle: string;
  currentPath: string;
  historyIndex: number;
  historyLength: number;
  breadcrumb: WorkspaceBreadcrumbPart[];
  dropTargetPath: string | null;
  onBack: () => void;
  onForward: () => void;
  onUp: () => void;
  onReturnToFiles: () => void;
  onNavigate: (path: string) => void;
  onDragOverDirectory: (event: DragEvent<HTMLButtonElement>, path: string) => void;
  onDropDirectory: (event: DragEvent<HTMLButtonElement>, path: string) => void | Promise<void>;
};

export function WorkspaceFileBreadcrumb({
  viewMode,
  isPersonalWorkspace,
  rootTitle,
  currentPath,
  historyIndex,
  historyLength,
  breadcrumb,
  dropTargetPath,
  onBack,
  onForward,
  onUp,
  onReturnToFiles,
  onNavigate,
  onDragOverDirectory,
  onDropDirectory,
}: WorkspaceFileBreadcrumbProps) {
  return (
    <nav className="workspace-file-breadcrumb" aria-label={isPersonalWorkspace ? "个人文件路径" : "项目文件路径"}>
      {viewMode === "files" ? (
        <div className="workspace-file-nav-controls" aria-label="文件导航" role="group">
          <button aria-label="后退" className="workspace-file-action" disabled={historyIndex <= 0} onClick={onBack} title="后退" type="button"><ChevronLeftIcon /></button>
          <button aria-label="前进" className="workspace-file-action" disabled={historyIndex >= historyLength - 1} onClick={onForward} title="前进" type="button"><ChevronRightIcon /></button>
          <button aria-label="上一级" className="workspace-file-action" disabled={!currentPath} onClick={onUp} title="上一级" type="button"><ArrowUpIcon /></button>
        </div>
      ) : (
        <div className="workspace-file-nav-controls" aria-label="文件导航" role="group">
          <button aria-label="返回项目文件" className="workspace-file-action" onClick={onReturnToFiles} title="返回项目文件" type="button"><ChevronLeftIcon /></button>
        </div>
      )}
      <div className="workspace-file-address-bar">
        {viewMode === "trash" ? (
          <>
            <button
              aria-label="根目录"
              className="workspace-file-address-root"
              onClick={onReturnToFiles}
              title={rootTitle}
              type="button"
            >
              <WorkspaceIcon />
            </button>
            <span className="workspace-file-path-separator" aria-hidden="true">›</span>
            <button
              className="workspace-file-path-segment"
              onClick={onReturnToFiles}
              type="button"
            >
              根目录
            </button>
            <span className="workspace-file-path-separator" aria-hidden="true">›</span>
            <span className="workspace-file-path-segment">回收站</span>
          </>
        ) : (
          <>
            <button
              aria-label="根目录"
              className="workspace-file-address-root"
              data-drop-target={dropTargetPath === "" ? "true" : undefined}
              onClick={() => onNavigate("")}
              onDragOver={(event) => onDragOverDirectory(event, "")}
              onDrop={(event) => void onDropDirectory(event, "")}
              title={rootTitle}
              type="button"
            >
              <WorkspaceIcon />
            </button>
            <span className="workspace-file-path-separator" aria-hidden="true">›</span>
            <button
              className="workspace-file-path-segment"
              data-drop-target={dropTargetPath === "" ? "true" : undefined}
              onClick={() => onNavigate("")}
              onDragOver={(event) => onDragOverDirectory(event, "")}
              onDrop={(event) => void onDropDirectory(event, "")}
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
                  onClick={() => onNavigate(part.path)}
                  onDragOver={(event) => onDragOverDirectory(event, part.path)}
                  onDrop={(event) => void onDropDirectory(event, part.path)}
                  type="button"
                >
                  {part.name}
                </button>
              </span>
            ))}
          </>
        )}
      </div>
    </nav>
  );
}
