import {
  AgentIcon,
  BrainIcon,
  EditIcon,
  NoteIcon,
  PlusIcon,
  RefreshIcon,
} from "../../../shared/icons/LineIcons";

type WorkspaceMeetingToolbarProps = {
  refreshing: boolean;
  isLegitimateMeetingFolder: boolean;
  onMediaTranscribe: () => void;
  onOpenTranscriptForm: () => void;
  onOpenSpeakerMap: () => void;
  onOpenTermCorrections: () => void;
  onGenerateMinutes: () => void;
  onRegenerateMinutes: () => void;
  onIngestMeeting: () => void;
  onIngestActionsOnly: () => void;
  onRetryTranscribe: () => void;
  onRetryGenerateMinutes: () => void;
};

export function WorkspaceMeetingToolbar({
  refreshing,
  isLegitimateMeetingFolder,
  onMediaTranscribe,
  onOpenTranscriptForm,
  onOpenSpeakerMap,
  onOpenTermCorrections,
  onGenerateMinutes,
  onRegenerateMinutes,
  onIngestMeeting,
  onIngestActionsOnly,
  onRetryTranscribe,
  onRetryGenerateMinutes,
}: WorkspaceMeetingToolbarProps) {
  const meetingFolderTitle = "请在具体会议文件夹中使用此功能。";

  return (
    <div className="workspace-meeting-toolbar" data-testid="meeting-toolbar">
      <span className="workspace-meeting-toolbar-label">会议工作流</span>
      <div className="workspace-meeting-toolbar-actions">
        <button
          className="workspace-file-primary-action"
          disabled={refreshing}
          onClick={onMediaTranscribe}
          title="上传会议音文件到当前文件夹并自动转录"
          type="button"
        >
          <PlusIcon /><span>上传/转写录音</span>
        </button>
        <button
          className="workspace-file-primary-action"
          disabled={refreshing}
          onClick={onOpenTranscriptForm}
          title="将已有的会议转录文本保存到当前文件夹"
          type="button"
        >
          <NoteIcon /><span>保存转录文本</span>
        </button>
        <button
          className="workspace-file-primary-action"
          disabled={!isLegitimateMeetingFolder || refreshing}
          onClick={onOpenSpeakerMap}
          title={!isLegitimateMeetingFolder ? meetingFolderTitle : "为当前会议的检测说话人设置显示名称"}
          type="button"
        >
          <AgentIcon /><span>说话人映射</span>
        </button>
        <button
          className="workspace-file-primary-action"
          disabled={!isLegitimateMeetingFolder || refreshing}
          onClick={onOpenTermCorrections}
          title={!isLegitimateMeetingFolder ? meetingFolderTitle : "添加需要纠正的术语"}
          type="button"
        >
          <EditIcon /><span>术语纠错</span>
        </button>
        <button
          className="workspace-file-primary-action"
          disabled={!isLegitimateMeetingFolder || refreshing}
          onClick={onGenerateMinutes}
          title={!isLegitimateMeetingFolder ? meetingFolderTitle : "从当前会议的转录文本生成纪要与行动项"}
          type="button"
        >
          <NoteIcon /><span>生成纪要与行动项</span>
        </button>
        <button
          className="workspace-file-primary-action"
          disabled={!isLegitimateMeetingFolder || refreshing}
          onClick={onRegenerateMinutes}
          title="如果会议转录已更新，重新生成纪要与行动项（创建新版本）"
          type="button"
        >
          <RefreshIcon /><span>重跑纪要</span>
        </button>
        <button
          className="workspace-file-primary-action"
          disabled={!isLegitimateMeetingFolder || refreshing}
          onClick={onIngestMeeting}
          title={!isLegitimateMeetingFolder ? meetingFolderTitle : "将当前会议组合成 GBrain-ready 页面"}
          type="button"
        >
          <BrainIcon /><span>录入此会议</span>
        </button>
        {isLegitimateMeetingFolder ? (
          <button
            className="workspace-file-primary-action"
            disabled={refreshing}
            onClick={onIngestActionsOnly}
            title="仅录入行动项，不包含纪要和转录上下文"
            type="button"
          >
            <BrainIcon /><span>录入行动项</span>
          </button>
        ) : null}
        {isLegitimateMeetingFolder ? (
          <>
            <button
              className="workspace-file-primary-action"
              disabled={refreshing}
              onClick={onRetryTranscribe}
              title="重试之前失败的音视频转录操作"
              type="button"
            >
              <RefreshIcon /><span>重试转录</span>
            </button>
            <button
              className="workspace-file-primary-action"
              disabled={refreshing}
              onClick={onRetryGenerateMinutes}
              title="重试之前失败的纪要生成操作"
              type="button"
            >
              <RefreshIcon /><span>重试纪要生成</span>
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}
