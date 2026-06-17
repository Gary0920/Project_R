import type { RefObject } from "react";

import {
  AgentIcon,
  BrainIcon,
  CopyIcon,
  EditIcon,
  MoreIcon,
  NoteIcon,
  PlusIcon,
  RefreshIcon,
  TrashIcon,
  WorkspaceIcon,
} from "../../../shared/icons/LineIcons";

export type WorkspaceFilePanelHeaderProps = {
  actionMenuOpen: boolean;
  canPasteInto: (targetDirectory: string) => boolean;
  canShowKnowledgeGraph: boolean;
  canShowKnowledgeIngest: boolean;
  currentPath: string;
  fileInputRef: RefObject<HTMLInputElement | null>;
  handleClearTrash: () => void | Promise<void>;
  handleCreateFolder: () => void;
  handleGenerateMinutes: (regenerate?: boolean) => void | Promise<void>;
  handleIngestMeeting: (actionsOnly?: boolean) => void | Promise<void>;
  handleMediaTranscribe: () => void;
  handleOpenKnowledgeGraph: () => void | Promise<void>;
  handleOpenSpeakerMap: () => void | Promise<void>;
  handleOpenTranscriptForm: () => void;
  handlePaste: (targetDirectory?: string) => void | Promise<void>;
  handleRefreshKnowledge: (path?: string, recursive?: boolean) => void;
  handleUpload: (fileList: FileList | File[] | null) => void | Promise<void>;
  isInMeetingFolder: boolean;
  isPersonalWorkspace: boolean;
  knowledgeGraphLabel: string;
  knowledgeGraphLoading: boolean;
  loading: boolean;
  navigateTo: (path: string) => void;
  panelSubtitle: string;
  pendingIngestCount: number;
  refresh: () => Promise<void>;
  refreshingKnowledge: boolean;
  setActionMenuOpen: (value: boolean | ((current: boolean) => boolean)) => void;
  setTermCorrectionsOpen: (value: boolean) => void;
  setViewMode: (value: "files" | "trash") => void;
  showMeetingWorkflowToolbar: boolean;
  viewMode: "files" | "trash";
  workspaceKind: string;
  workspaceName?: string;
};

export function WorkspaceFilePanelHeader({
  actionMenuOpen,
  canPasteInto,
  canShowKnowledgeGraph,
  canShowKnowledgeIngest,
  currentPath,
  fileInputRef,
  handleClearTrash,
  handleCreateFolder,
  handleGenerateMinutes,
  handleIngestMeeting,
  handleMediaTranscribe,
  handleOpenKnowledgeGraph,
  handleOpenSpeakerMap,
  handleOpenTranscriptForm,
  handlePaste,
  handleRefreshKnowledge,
  handleUpload,
  isInMeetingFolder,
  isPersonalWorkspace,
  knowledgeGraphLabel,
  knowledgeGraphLoading,
  loading,
  navigateTo,
  panelSubtitle,
  pendingIngestCount,
  refresh,
  refreshingKnowledge,
  setActionMenuOpen,
  setTermCorrectionsOpen,
  setViewMode,
  showMeetingWorkflowToolbar,
  viewMode,
  workspaceKind,
  workspaceName,
}: WorkspaceFilePanelHeaderProps) {
  return (
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
                  {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                    <button onClick={() => { setActionMenuOpen(false); handleOpenTranscriptForm(); }} type="button"><RefreshIcon />保存转录文本</button>
                  ) : null}
                  {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                    <button onClick={() => { setActionMenuOpen(false); void handleGenerateMinutes(); }} type="button"><NoteIcon />生成纪要与行动项</button>
                  ) : null}
                  {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                    <button onClick={() => { setActionMenuOpen(false); void handleOpenSpeakerMap(); }} type="button"><AgentIcon />说话人映射</button>
                  ) : null}
                  {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                    <button onClick={() => { setActionMenuOpen(false); void handleGenerateMinutes(true); }} type="button"><RefreshIcon />应用修正并重跑纪要</button>
                  ) : null}
                  {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                    <button onClick={() => { setActionMenuOpen(false); setTermCorrectionsOpen(true); }} type="button"><EditIcon />术语纠错</button>
                  ) : null}
                  {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                    <button onClick={() => { setActionMenuOpen(false); void handleMediaTranscribe(); }} type="button"><PlusIcon />上传会议音视频</button>
                  ) : null}
                  {isInMeetingFolder && workspaceKind !== "user" && !showMeetingWorkflowToolbar ? (
                    <button onClick={() => { setActionMenuOpen(false); void handleIngestMeeting(); }} type="button"><BrainIcon />录入此会议</button>
                  ) : null}
                  {canShowKnowledgeIngest ? (
                    <button disabled={refreshingKnowledge || pendingIngestCount === 0} onClick={() => { setActionMenuOpen(false); handleRefreshKnowledge(currentPath, true); }} type="button"><RefreshIcon />{refreshingKnowledge ? "正在录入..." : `录入当前文件夹${pendingIngestCount > 0 ? ` (${pendingIngestCount})` : ""}`}</button>
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
  );
}
