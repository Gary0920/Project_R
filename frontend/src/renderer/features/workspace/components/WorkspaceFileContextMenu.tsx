import type { Dispatch, SetStateAction } from "react";

import {
  fetchWorkspaceFileBlob,
  generateMeetingMinutesAndActions,
  ingestMeetingToGBrain,
  saveMeetingTranscript,
  saveMeetingTranscriptFromFile,
  transcribeMeetingMedia,
} from "../api";
import {
  inferMeetingFolder,
  isMeetingAudioFile,
  isMeetingTranscriptSourceFile,
} from "../workspaceMeetingUtils";
import {
  countPendingIngestFiles,
  isTrashPath,
  isTrashWorkspaceItem,
} from "../workspaceFilePanelUtils";
import type { ApiClientOptions } from "../../../shared/api/client";
import type { AgentRunResponse, WorkspaceFileItemResponse } from "../../../shared/api/types";
import {
  ArchiveIcon,
  BrainIcon,
  CopyIcon,
  EditIcon,
  MoveIcon,
  NoteIcon,
  RefreshIcon,
  TrashIcon,
  WorkspaceIcon,
} from "../../../shared/icons/LineIcons";
import type { WorkspaceConfirmation } from "./WorkspaceDialogs";
import type { WorkspaceFileContextMenu as WorkspaceFileContextMenuState } from "./workspaceFilePanelTypes";

export type WorkspaceFileContextMenuProps = {
  activateFileItem: (item: WorkspaceFileItemResponse) => void;
  apiOptions: ApiClientOptions;
  canCopyWorkspaceItem: (item: WorkspaceFileItemResponse) => boolean;
  canModifyWorkspaceItem: (item: WorkspaceFileItemResponse) => boolean;
  canPasteInto: (targetDirectory: string) => boolean;
  canShowKnowledgeIngest: boolean;
  contextMenu: WorkspaceFileContextMenuState;
  downloadWorkspaceFile: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  handleCopy: (item: WorkspaceFileItemResponse) => void;
  handleCreateFolder: (parentPath?: string) => void;
  handleCut: (item: WorkspaceFileItemResponse) => void;
  handleDelete: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  handleGenerateMinutes: (regenerate?: boolean) => void | Promise<void>;
  handleIngestMeeting: (actionsOnly?: boolean) => void | Promise<void>;
  handlePaste: (targetDirectory?: string) => void | Promise<void>;
  handleRefreshKnowledge: (path?: string, recursive?: boolean, item?: WorkspaceFileItemResponse) => void;
  handleRename: (item: WorkspaceFileItemResponse) => void;
  loading: boolean;
  onReferenceFile?: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  openFilePreview: (item: WorkspaceFileItemResponse) => void | Promise<void>;
  refresh: () => Promise<void>;
  refreshingKnowledge: boolean;
  runContextAction: (action: () => void | Promise<void>) => void;
  setCurrentPath: (path: string) => void;
  setError: (message: string | null) => void;
  setLatestAgentRun: Dispatch<SetStateAction<AgentRunResponse | null>>;
  setNotice: (message: string | null) => void;
  setPendingConfirmation: (confirmation: WorkspaceConfirmation) => void;
  setRefreshingKnowledge: (value: boolean) => void;
  workspaceId: number | null;
  workspaceKind: string;
  workspaceName?: string;
};

export function WorkspaceFileContextMenu({
  activateFileItem,
  apiOptions,
  canCopyWorkspaceItem,
  canModifyWorkspaceItem,
  canPasteInto,
  canShowKnowledgeIngest,
  contextMenu,
  downloadWorkspaceFile,
  handleCopy,
  handleCreateFolder,
  handleCut,
  handleDelete,
  handleGenerateMinutes,
  handleIngestMeeting,
  handlePaste,
  handleRefreshKnowledge,
  handleRename,
  loading,
  onReferenceFile,
  openFilePreview,
  refresh,
  refreshingKnowledge,
  runContextAction,
  setCurrentPath,
  setError,
  setLatestAgentRun,
  setNotice,
  setPendingConfirmation,
  setRefreshingKnowledge,
  workspaceId,
  workspaceKind,
  workspaceName,
}: WorkspaceFileContextMenuProps) {
  return (
    <div
      className="workspace-file-context-menu"
      onClick={(event) => event.stopPropagation()}
      style={{ left: contextMenu.x, top: contextMenu.y }}
    >
      {contextMenu.kind === "blank" ? (
        <>
          <button disabled={loading} onClick={() => runContextAction(() => void refresh())} type="button"><RefreshIcon />刷新</button>
          <button disabled={!canPasteInto(contextMenu.targetDirectory)} onClick={() => runContextAction(() => void handlePaste(contextMenu.targetDirectory))} type="button"><CopyIcon />粘贴到此处</button>
          <button disabled={isTrashPath(contextMenu.targetDirectory)} onClick={() => runContextAction(() => handleCreateFolder(contextMenu.targetDirectory))} type="button"><WorkspaceIcon />新建文件夹</button>
        </>
      ) : contextMenu.item?.type === "directory" ? (
        <>
          <button onClick={() => runContextAction(() => activateFileItem(contextMenu.item!))} type="button">{isTrashWorkspaceItem(contextMenu.item) ? <TrashIcon /> : <WorkspaceIcon />}{isTrashWorkspaceItem(contextMenu.item) ? "打开回收站" : "打开"}</button>
          <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCut(contextMenu.item!))} type="button"><MoveIcon />剪切</button>
          <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canCopyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCopy(contextMenu.item!))} type="button"><CopyIcon />复制</button>
          <button disabled={!canPasteInto(contextMenu.item.path)} onClick={() => runContextAction(() => void handlePaste(contextMenu.item!.path))} type="button"><CopyIcon />粘贴到此处</button>
          {canShowKnowledgeIngest ? (
            <button
              disabled={refreshingKnowledge || countPendingIngestFiles([contextMenu.item]) === 0 || isTrashWorkspaceItem(contextMenu.item)}
              onClick={() => runContextAction(() => handleRefreshKnowledge(contextMenu.item!.path, true, contextMenu.item))}
              type="button"
            >
              <RefreshIcon />录入此文件夹
            </button>
          ) : null}
          <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleRename(contextMenu.item!))} type="button"><EditIcon />重命名</button>
          <button disabled={isTrashWorkspaceItem(contextMenu.item) || !canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => void handleDelete(contextMenu.item!))} type="button"><TrashIcon />删除</button>
        </>
      ) : contextMenu.item ? (
        <>
          <button onClick={() => runContextAction(() => openFilePreview(contextMenu.item!))} type="button"><NoteIcon />预览</button>
          <button onClick={() => runContextAction(() => void downloadWorkspaceFile(contextMenu.item!))} type="button"><ArchiveIcon />下载</button>
          <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCut(contextMenu.item!))} type="button"><MoveIcon />剪切</button>
          <button disabled={!canCopyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleCopy(contextMenu.item!))} type="button"><CopyIcon />复制</button>
          {canShowKnowledgeIngest ? (
            <button
              disabled={refreshingKnowledge || countPendingIngestFiles([contextMenu.item]) === 0 || isTrashWorkspaceItem(contextMenu.item)}
              onClick={() => runContextAction(() => handleRefreshKnowledge(contextMenu.item!.path, false, contextMenu.item))}
              type="button"
            >
              <RefreshIcon />录入此文件
            </button>
          ) : null}
          {canShowKnowledgeIngest && contextMenu.item && !isTrashWorkspaceItem(contextMenu.item)
            && contextMenu.item.name === "actions-latest.md"
            && inferMeetingFolder(contextMenu.item.path) !== null ? (
            <button
              disabled={refreshingKnowledge}
              onClick={() => runContextAction(async () => {
                if (!workspaceId) return;
                setCurrentPath(inferMeetingFolder(contextMenu.item!.path)!);
                setPendingConfirmation({
                  title: "录入行动项（仅行动项）",
                  detail: [
                    `当前工作区：${workspaceName ?? workspaceKind}`,
                    `路径：${inferMeetingFolder(contextMenu.item!.path)!}/05-行动项/actions-latest.md`,
                    "范围：仅录入行动项文件，不包含会议纪要和转录文本。",
                    "将标记为「仅行动项」，低上下文完整度。",
                    "如需要完整会议知识，建议改为录入完整会议。",
                  ].join("\\n"),
                  confirmLabel: "录入行动项",
                  tone: "warning",
                  onConfirm: async () => {
                    await handleIngestMeeting(true);
                  },
                });
              })}
              type="button"
            >
              <BrainIcon />录入行动项（仅行动项）
            </button>
          ) : null}
          {contextMenu.item && !isTrashWorkspaceItem(contextMenu.item)
            && contextMenu.item.rag_status === "failed" ? (
            <button
              disabled={refreshingKnowledge}
              onClick={() => runContextAction(() => {
                handleRefreshKnowledge(
                  contextMenu.item!.path,
                  false,
                  contextMenu.item,
                );
              })}
              type="button"
            >
              <RefreshIcon />重新处理此文件
            </button>
          ) : null}
          {contextMenu.item && !isTrashWorkspaceItem(contextMenu.item)
            && contextMenu.item.name?.startsWith("transcript-")
            && (contextMenu.item.rag_status === "failed" || contextMenu.item.rag_status === "partial")
            && inferMeetingFolder(contextMenu.item.path) !== null ? (
            <button
              disabled={refreshingKnowledge}
              onClick={() => runContextAction(async () => {
                if (!workspaceId) return;
                setCurrentPath(inferMeetingFolder(contextMenu.item!.path)!);
                setPendingConfirmation({
                  title: "重新生成纪要与行动项",
                  detail: `基于现有转录重新生成纪要与行动项。转录状态为 ${contextMenu.item!.rag_status}，部分失败内容可能无法覆盖。`,
                  confirmLabel: "重新生成",
                  tone: "warning",
                  onConfirm: async () => {
                    await handleGenerateMinutes(true);
                  },
                });
              })}
              type="button"
            >
              <NoteIcon />重新生成纪要
            </button>
          ) : null}
          {contextMenu.item && !isTrashWorkspaceItem(contextMenu.item) && inferMeetingFolder(contextMenu.item.path) !== null && (
            <MeetingFileContextActions
              apiOptions={apiOptions}
              contextMenu={contextMenu}
              handleGenerateMinutes={handleGenerateMinutes}
              handleIngestMeeting={handleIngestMeeting}
              refresh={refresh}
              refreshingKnowledge={refreshingKnowledge}
              runContextAction={runContextAction}
              setError={setError}
              setLatestAgentRun={setLatestAgentRun}
              setNotice={setNotice}
              setPendingConfirmation={setPendingConfirmation}
              setRefreshingKnowledge={setRefreshingKnowledge}
              workspaceId={workspaceId}
            />
          )}
          <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => handleRename(contextMenu.item!))} type="button"><EditIcon />重命名</button>
          <button disabled={!canModifyWorkspaceItem(contextMenu.item)} onClick={() => runContextAction(() => void handleDelete(contextMenu.item!))} type="button"><TrashIcon />删除</button>
          <button onClick={() => runContextAction(() => void onReferenceFile?.(contextMenu.item!))} type="button"><NoteIcon />引用文件</button>
          <button onClick={() => runContextAction(() => void openFilePreview(contextMenu.item!))} type="button"><NoteIcon />详细信息</button>
        </>
      ) : null}
    </div>
  );
}

function MeetingFileContextActions({
  apiOptions,
  contextMenu,
  handleGenerateMinutes,
  refresh,
  refreshingKnowledge,
  runContextAction,
  setError,
  setLatestAgentRun,
  setNotice,
  setPendingConfirmation,
  setRefreshingKnowledge,
  workspaceId,
}: {
  apiOptions: ApiClientOptions;
  contextMenu: WorkspaceFileContextMenuState;
  handleGenerateMinutes: (regenerate?: boolean) => void | Promise<void>;
  handleIngestMeeting: (actionsOnly?: boolean) => void | Promise<void>;
  refresh: () => Promise<void>;
  refreshingKnowledge: boolean;
  runContextAction: (action: () => void | Promise<void>) => void;
  setError: (message: string | null) => void;
  setLatestAgentRun: Dispatch<SetStateAction<AgentRunResponse | null>>;
  setNotice: (message: string | null) => void;
  setPendingConfirmation: (confirmation: WorkspaceConfirmation) => void;
  setRefreshingKnowledge: (value: boolean) => void;
  workspaceId: number | null;
}) {
  const item = contextMenu.item;
  if (!item) return null;
  const meetingFolder = inferMeetingFolder(item.path);
  if (!meetingFolder) return null;

  return (
    <>
      {isMeetingAudioFile(item.name) ? (
        <button
          disabled={refreshingKnowledge}
          onClick={() => runContextAction(async () => {
            if (!workspaceId) return;
            setNotice("正在读取文件并转录...");
            setRefreshingKnowledge(true);
            try {
              const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
              const file = new File([blob], item.name, { type: blob.type });
              const resp = await transcribeMeetingMedia(apiOptions, workspaceId, meetingFolder, file);
              if (resp.agent_run) setLatestAgentRun(resp.agent_run);
              const parts: string[] = [];
              if (resp.transcription_status === "failed") parts.push("转录失败");
              else if (resp.transcription_status === "partial") parts.push(`部分转录完成（${resp.segment_count}段）`);
              else parts.push(`转录完成（${resp.segment_count}段）`);
              if (resp.warnings.length > 0) parts.push(`${resp.warnings.length} 条警告`);
              if (resp.token_cost > 0) parts.push(`token：${resp.token_cost}`);
              setNotice(parts.join("，"));
              await refresh();
            } catch (txErr: unknown) {
              setError(txErr instanceof Error ? txErr.message : "转录失败");
            } finally {
              setRefreshingKnowledge(false);
            }
          })}
          type="button"
        >
          <NoteIcon />转录此音视频
        </button>
      ) : null}
      {isMeetingTranscriptSourceFile(item) ? (
        <button
          disabled={refreshingKnowledge}
          onClick={() => runContextAction(async () => {
            if (!workspaceId) return;
            setNotice("正在保存转录文本并生成纪要...");
            setRefreshingKnowledge(true);
            try {
              const blob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
              const lower = item.name.toLowerCase();
              if (lower.endsWith(".docx")) {
                const file = new File([blob], item.name, { type: blob.type });
                await saveMeetingTranscriptFromFile(apiOptions, workspaceId, meetingFolder, file);
              } else {
                const text = await blob.text();
                await saveMeetingTranscript(apiOptions, workspaceId, {
                  folder_path: meetingFolder,
                  content: text,
                  input_type: lower.endsWith(".md") ? "md" : "txt",
                  original_filename: item.name,
                });
              }
              const genResp = await generateMeetingMinutesAndActions(apiOptions, workspaceId, { folder_path: meetingFolder });
              if (genResp.agent_run) setLatestAgentRun(genResp.agent_run);
              setNotice(`纪要已生成（模型：${genResp.model_used}）`);
              await refresh();
            } catch (genErr: unknown) {
              if (genErr instanceof Error && genErr.message.includes("已存在纪要与行动项")) {
                setPendingConfirmation({
                  title: "已存在纪要与行动项",
                  detail: "当前会议已有纪要与行动项。重新生成将创建新版本（v2/v3…）并更新 latest。是否继续？",
                  confirmLabel: "重新生成",
                  tone: "warning",
                  onConfirm: async () => {
                    if (!workspaceId || !meetingFolder) return;
                    setRefreshingKnowledge(true);
                    try {
                      const reBlob = await fetchWorkspaceFileBlob(apiOptions, workspaceId, item.path);
                      const reLower = item.name.toLowerCase();
                      if (reLower.endsWith(".docx")) {
                        await saveMeetingTranscriptFromFile(apiOptions, workspaceId, meetingFolder, new File([reBlob], item.name, { type: reBlob.type }));
                      } else {
                        const reText = await reBlob.text();
                        await saveMeetingTranscript(apiOptions, workspaceId, { folder_path: meetingFolder, content: reText, input_type: reLower.endsWith(".md") ? "md" : "txt", original_filename: item.name });
                      }
                      const reGenResp = await generateMeetingMinutesAndActions(apiOptions, workspaceId, { folder_path: meetingFolder, regenerate: true });
                      if (reGenResp.agent_run) setLatestAgentRun(reGenResp.agent_run);
                      setNotice(`纪要已重新生成（模型：${reGenResp.model_used}）`);
                      await refresh();
                    } catch (reErr: unknown) {
                      setError(reErr instanceof Error ? reErr.message : "重新生成失败");
                    } finally {
                      setRefreshingKnowledge(false);
                    }
                  },
                });
                return;
              }
              setError(genErr instanceof Error ? genErr.message : "生成纪要失败");
            } finally {
              setRefreshingKnowledge(false);
            }
          })}
          type="button"
        >
          <NoteIcon />用此转录生成纪要
        </button>
      ) : null}
      {item.name === "actions-latest.md" ? (
        <button
          disabled={refreshingKnowledge}
          onClick={() => runContextAction(async () => {
            if (!workspaceId) return;
            setRefreshingKnowledge(true);
            setError(null);
            try {
              const resp = await ingestMeetingToGBrain(apiOptions, workspaceId, {
                folder_path: meetingFolder,
                single_file_path: item.path,
              });
              const msgs = [`已录入 ${resp.ingested_files.length} 个文件`];
              if (resp.warning) msgs.push(`注意：${resp.warning}`);
              setNotice(msgs.join("，"));
              if (resp.agent_run) setLatestAgentRun(resp.agent_run);
              await refresh();
            } catch (ingestErr: unknown) {
              setError(ingestErr instanceof Error ? ingestErr.message : "录入失败");
            } finally {
              setRefreshingKnowledge(false);
            }
          })}
          type="button"
        >
          <BrainIcon />录入此行动项
        </button>
      ) : null}
    </>
  );
}
