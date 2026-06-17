import { useState, type ChangeEvent, type Dispatch, type SetStateAction } from "react";

import type { WorkspaceConfirmation } from "../components/WorkspaceDialogs";
import type { WorkspaceMeetingFolderForm } from "../components/WorkspaceMeetingFolderDialog";
import type { WorkspaceMeetingTranscriptForm } from "../components/WorkspaceMeetingTranscriptDialog";
import type { WorkspaceMeetingTermCorrection } from "../components/WorkspaceMeetingTermCorrectionsDialog";
import {
  createMeetingFolder,
  generateMeetingMinutesAndActions,
  getMeetingSpeakers,
  ingestMeetingToGBrain,
  preflightMeetingMediaTranscribe,
  retryMeetingOperation,
  saveMeetingSpeakerMap,
  saveMeetingTermCorrections,
  saveMeetingTranscript,
  saveMeetingTranscriptFromFile,
  transcribeMeetingMedia,
} from "../api";
import type { ApiClientOptions } from "../../../shared/api/client";
import type {
  AgentRunResponse,
  DetectedSpeaker,
  MeetingFolderResponse,
  MeetingGenerateResponse,
  MeetingRetryResponse,
  MediaPreflightResponse,
  SaveMeetingTranscriptResponse,
} from "../../../shared/api/types";

export function useWorkspaceMeetingWorkflow({
  activeMeetingFolderPath,
  apiOptions,
  closeActionMenu,
  closeContextMenu,
  currentPath,
  navigateTo,
  refresh,
  setError,
  setLatestAgentRun,
  setNotice,
  setPendingConfirmation,
  setRefreshingKnowledge,
  workspaceId,
  workspaceKind,
  workspaceName,
}: {
  activeMeetingFolderPath: string;
  apiOptions: ApiClientOptions;
  closeActionMenu: () => void;
  closeContextMenu: () => void;
  currentPath: string;
  navigateTo: (path: string) => void;
  refresh: () => Promise<void>;
  setError: (message: string | null) => void;
  setLatestAgentRun: (run: AgentRunResponse) => void;
  setNotice: (message: string | null) => void;
  setPendingConfirmation: Dispatch<SetStateAction<WorkspaceConfirmation | null>>;
  setRefreshingKnowledge: (refreshing: boolean) => void;
  workspaceId: number | null;
  workspaceKind: string;
  workspaceName?: string;
}) {
  const [meetingFolderForm, setMeetingFolderForm] = useState<WorkspaceMeetingFolderForm>({ open: false, topic: "", meetingTime: "", meetingType: "其他", busy: false });
  const [meetingTranscriptForm, setMeetingTranscriptForm] = useState<WorkspaceMeetingTranscriptForm>({ open: false, folderPath: "", content: "", selectedFile: null, busy: false });
  const [speakerMapOpen, setSpeakerMapOpen] = useState(false);
  const [detectedSpeakers, setDetectedSpeakers] = useState<DetectedSpeaker[]>([]);
  const [speakerMapLoading, setSpeakerMapLoading] = useState(false);
  const [speakerMapNames, setSpeakerMapNames] = useState<Record<string, string>>({});
  const [termCorrectionsOpen, setTermCorrectionsOpen] = useState(false);
  const [termCorrections, setTermCorrections] = useState<WorkspaceMeetingTermCorrection[]>([]);
  const [termCorrectionsBusy, setTermCorrectionsBusy] = useState(false);
  const [termEditOriginal, setTermEditOriginal] = useState("");
  const [termEditCorrected, setTermEditCorrected] = useState("");

  // ── Meeting operations ──────────────────────────────────────────────────

  function openMeetingFolderForm() {
    if (!workspaceId) return;
    if (workspaceKind === "user") return;
    setMeetingFolderForm({ open: true, topic: "", meetingTime: "", meetingType: "其他", busy: false });
    closeContextMenu();
  }

  async function handleMeetingFolderCreate() {
    if (!workspaceId || meetingFolderForm.busy) return;
    const topic = meetingFolderForm.topic.trim();
    if (!topic) return;
    setMeetingFolderForm((prev) => ({ ...prev, busy: true }));
    setError(null);
    try {
      const data: { topic: string; meeting_time?: string; meeting_type?: string } = { topic, meeting_type: meetingFolderForm.meetingType };
      if (meetingFolderForm.meetingTime.trim()) {
        data.meeting_time = meetingFolderForm.meetingTime.trim();
      }
      const response: MeetingFolderResponse = await createMeetingFolder(apiOptions, workspaceId, data);
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`已创建会议文件夹：${response.meeting_folder_path}`);
      setMeetingFolderForm({ open: false, topic: "", meetingTime: "", meetingType: "其他", busy: false });
      await refresh();
      // Navigate into the new folder
      navigateTo(response.meeting_folder_path);
    } catch (folderError: unknown) {
      setError(folderError instanceof Error ? folderError.message : "创建会议文件夹失败");
    } finally {
      setMeetingFolderForm((prev) => ({ ...prev, busy: false }));
    }
  }

  function openMeetingTranscriptForm(folderPath?: string) {
    if (!workspaceId) return;
    if (workspaceKind === "user") return;
    setMeetingTranscriptForm({
      open: true,
      folderPath: folderPath ?? activeMeetingFolderPath,
      content: "",
      selectedFile: null,
      busy: false,
    });
    closeContextMenu();
  }

  function handleTranscriptFileSelect(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".txt") && !lower.endsWith(".md") && !lower.endsWith(".markdown") && !lower.endsWith(".docx")) {
      setError("仅支持 TXT / MD / DOCX 格式");
      return;
    }
    setMeetingTranscriptForm((prev) => ({ ...prev, selectedFile: file, content: "" }));
    // For TXT/MD, read content client-side to preview
    if (!lower.endsWith(".docx")) {
      const reader = new FileReader();
      reader.onload = () => {
        setMeetingTranscriptForm((prev) => ({
          ...prev,
          content: typeof reader.result === "string" ? reader.result : "",
        }));
      };
      reader.readAsText(file);
    }
  }

  async function handleMeetingTranscriptSave() {
    if (!workspaceId || meetingTranscriptForm.busy) return;
    const folderPath = meetingTranscriptForm.folderPath.trim();
    if (!folderPath) return;

    const hasFile = meetingTranscriptForm.selectedFile !== null;
    const content = meetingTranscriptForm.content.trim();
    if (!hasFile && !content) return;

    setMeetingTranscriptForm((prev) => ({ ...prev, busy: true }));
    setError(null);
    try {
      let response: SaveMeetingTranscriptResponse;

      if (hasFile && meetingTranscriptForm.selectedFile!.name.toLowerCase().endsWith(".docx")) {
        // DOCX: server-side extraction via file upload endpoint
        response = await saveMeetingTranscriptFromFile(
          apiOptions, workspaceId, folderPath, meetingTranscriptForm.selectedFile!,
        );
      } else if (hasFile) {
        // TXT/MD: already read client-side, submit as content
        const filename = meetingTranscriptForm.selectedFile!.name;
        const inputType = filename.toLowerCase().endsWith(".md") ? "md" : "txt";
        response = await saveMeetingTranscript(apiOptions, workspaceId, {
          folder_path: folderPath,
          content,
          input_type: inputType,
          original_filename: filename,
        });
      } else {
        // Paste
        response = await saveMeetingTranscript(apiOptions, workspaceId, {
          folder_path: folderPath,
          content,
          input_type: "paste",
        });
      }

      if (response.agent_run) setLatestAgentRun(response.agent_run);
      setNotice(`转录已保存：${response.transcript_latest_path}`);
      setMeetingTranscriptForm({ open: false, folderPath: "", content: "", selectedFile: null, busy: false });
      await refresh();
    } catch (transcriptError: unknown) {
      setError(transcriptError instanceof Error ? transcriptError.message : "保存转录失败");
    } finally {
      setMeetingTranscriptForm((prev) => ({ ...prev, busy: false }));
    }
  }

  async function handleGenerateMinutes(regenerate = false) {
    if (!workspaceId || !currentPath) return;
    if (workspaceKind === "user") return;
    const folderPath = activeMeetingFolderPath;
    setNotice("正在生成纪要与行动项...");
    setError(null);
    setRefreshingKnowledge(true);
    try {
      const response: MeetingGenerateResponse = await generateMeetingMinutesAndActions(
        apiOptions,
        workspaceId,
        { folder_path: folderPath, regenerate },
      );
      if (response.agent_run) setLatestAgentRun(response.agent_run);
      const details = [
        `纪要：${response.minutes_latest_path}`,
        `行动项：${response.actions_latest_path}`,
      ];
      if (response.model_used === "template-fallback") {
        setNotice(`纪要与行动项已保存（LLM 暂不可用，使用模板占位）。${details.join("；")}。`);
      } else {
        setNotice(`纪要与行动项已保存（${details.join("；")}，模型：${response.model_used}，token：${response.token_cost}）。可在文件面板中下载。`);
      }
      await refresh();
    } catch (genError: unknown) {
      if (genError instanceof Error && genError.message.includes("已存在纪要与行动项")) {
        // Offer to regenerate
        closeActionMenu();
        setPendingConfirmation({
          title: "已存在纪要与行动项",
          detail: "当前会议已有纪要与行动项。重新生成将创建新版本（v2/v3…）并更新 latest。是否继续？",
          confirmLabel: "重新生成",
          tone: "warning",
          onConfirm: async () => {
            await handleGenerateMinutes(true);
          },
        });
        return;
      }
      setError(genError instanceof Error ? genError.message : "生成纪要与行动项失败");
    } finally {
      setRefreshingKnowledge(false);
    }
  }

  async function handleOpenSpeakerMap() {
    if (!workspaceId || !currentPath) return;
    setSpeakerMapOpen(true);
    setSpeakerMapLoading(true);
    setDetectedSpeakers([]);
    setError(null);
    try {
      const response = await getMeetingSpeakers(apiOptions, workspaceId, activeMeetingFolderPath);
      const speakers = response.detected_speakers ?? [];
      setDetectedSpeakers(speakers);
      // Initialize name map with detected display names
      const nameMap: Record<string, string> = {};
      for (const sp of speakers) {
        nameMap[sp.speaker_id] = sp.display_name;
      }
      setSpeakerMapNames(nameMap);
    } catch (speakerError: unknown) {
      setError(speakerError instanceof Error ? speakerError.message : "获取说话人信息失败");
      setSpeakerMapOpen(false);
    } finally {
      setSpeakerMapLoading(false);
    }
  }

  async function handleSaveSpeakerMap() {
    if (!workspaceId || !currentPath) return;
    setSpeakerMapLoading(true);
    setError(null);
    try {
      const speakers = detectedSpeakers.map((sp) => ({
        speaker_id: sp.speaker_id,
        display_name: speakerMapNames[sp.speaker_id] ?? sp.display_name,
      }));
      await saveMeetingSpeakerMap(apiOptions, workspaceId, {
        folder_path: activeMeetingFolderPath,
        speakers,
      });
      setNotice("说话人映射已保存。点击「应用修正并重跑纪要」可更新纪要。");
      setSpeakerMapOpen(false);
      await refresh();
    } catch (mapError: unknown) {
      setError(mapError instanceof Error ? mapError.message : "保存说话人映射失败");
    } finally {
      setSpeakerMapLoading(false);
    }
  }

  async function handleSaveTermCorrections() {
    if (!workspaceId || !currentPath) return;
    setTermCorrectionsBusy(true);
    setError(null);
    try {
      await saveMeetingTermCorrections(apiOptions, workspaceId, {
        folder_path: activeMeetingFolderPath,
        corrections: termCorrections,
      });
      setNotice("术语纠错已保存。");
      setTermCorrectionsOpen(false);
      setTermCorrections([]);
      await refresh();
    } catch (termErr: unknown) {
      setError(termErr instanceof Error ? termErr.message : "保存术语纠错失败");
    } finally {
      setTermCorrectionsBusy(false);
    }
  }

  async function handleIngestMeeting(actionsOnly = false) {
    if (!workspaceId || !currentPath) return;
    const sourceScope = workspaceKind === "customer" ? "CRM 客户情报" : "项目知识库";
    const scopeLabel = workspaceKind === "customer" ? "客户情报" : "当前项目";
    const detailLines = [
      `当前工作区：${workspaceName ?? workspaceKind}`,
      `目标 source：${sourceScope}（${scopeLabel}）`,
      `路径：${activeMeetingFolderPath}`,
    ];
    if (actionsOnly) {
      detailLines.push("范围：仅录入行动项文件 actions-latest.md");
      detailLines.push("将标记为「仅行动项」，低上下文完整度");
      detailLines.push("建议：如需要完整会议知识，请改为录入完整会议（纪要和转录）。");
    } else {
      detailLines.push("将取 latest 版本组合成 GBrain-ready 页面，旧版本标记为已取代。");
      detailLines.push("生成后需在 GBrain 管理端同步（本操作不自动触发 sync）。");
    }
    detailLines.push("原始音视频不直接录入。");
    detailLines.push("仅工作区管理员可操作。");

    setPendingConfirmation({
      title: actionsOnly ? "录入行动项（仅行动项）" : "录入此会议",
      detail: detailLines.join("\\n"),
      confirmLabel: "确认录入",
      tone: "warning",
      onConfirm: async () => {
        setRefreshingKnowledge(true);
        setError(null);
        try {
          const ingestData: { folder_path: string; recursive?: boolean; single_file_path?: string } = {
            folder_path: activeMeetingFolderPath,
          };
          if (actionsOnly) {
            ingestData.single_file_path = `${activeMeetingFolderPath}/05-行动项/actions-latest.md`;
          }
          const resp = await ingestMeetingToGBrain(apiOptions, workspaceId!, ingestData);
          const msgs = [`已录入 ${resp.ingested_files.length} 个文件`];
          if (resp.skipped_files.length > 0) {
            msgs.push(`跳过 ${resp.skipped_files.length} 个旧版本`);
          }
          msgs.push(`source：${resp.source_id}`);
          if (resp.warning) {
            msgs.push(`注意：${resp.warning}`);
          }
          setNotice(msgs.join("，"));
          if (resp.agent_run) setLatestAgentRun(resp.agent_run);
          await refresh();
        } catch (ingestErr: unknown) {
          setError(ingestErr instanceof Error ? ingestErr.message : "录入失败");
        } finally {
          setRefreshingKnowledge(false);
        }
      },
    });
  }

  function niceSaveSummary(filePath: string, status: string) {
    const statusLabel = status === "failed" ? "失败" : status === "partial" ? "部分完成" : "完成";
    setNotice(`已保存：${filePath}（${statusLabel}）。可下载或在文件面板查看。`);
  }

  async function handleRetryMeeting(operation: "transcribe" | "generate_minutes") {
    if (!workspaceId || !currentPath) return;
    setRefreshingKnowledge(true);
    setError(null);
    try {
      const resp: MeetingRetryResponse = await retryMeetingOperation(apiOptions, workspaceId!, {
        folder_path: activeMeetingFolderPath,
        operation,
      });
      if (resp.agent_run) setLatestAgentRun(resp.agent_run);
      setNotice(`重试完成：${resp.message}`);
      await refresh();
    } catch (retryErr: unknown) {
      setError(retryErr instanceof Error ? retryErr.message : "重试失败");
    } finally {
      setRefreshingKnowledge(false);
    }
  }

  function handleMediaTranscribe() {
    if (!workspaceId || !currentPath) return;
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".mp3,.wav,.m4a,.ogg,.flac,.mp4,.mov,.avi,.wmv,.mkv,.webm";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const sizeMB = file.size / (1024 * 1024);
      const isVideo = !!file.name.match(/\.(mp4|mov|avi|wmv|mkv|webm)$/i);

      // Attempt preflight for accurate duration estimate
      let preflight: MediaPreflightResponse | null = null;
      try {
        preflight = await preflightMeetingMediaTranscribe(apiOptions, workspaceId!, {
          folder_path: activeMeetingFolderPath,
          filename: file.name,
          size_bytes: file.size,
          content_type: file.type,
        });
      } catch {
        // Preflight unavailable; fall back to rough estimate
      }

      const estMin = preflight?.estimated_duration_minutes
        ?? (isVideo ? Math.max(1, Math.round(sizeMB / 8)) : Math.max(1, Math.round(sizeMB)));
      const estSeg = preflight?.estimated_segments ?? Math.max(1, Math.ceil(estMin / 5));
      const isLong = preflight?.is_long_media ?? (estMin > 30);

      const details: string[] = [
        `当前工作区：${workspaceName ?? workspaceKind}`,
        `目标路径：${activeMeetingFolderPath}`,
        `文件：${file.name}`,
        `大小：${sizeMB.toFixed(1)} MB`,
        `预估时长：约 ${estMin} 分钟`,
      ];

      if (isLong) {
        details.push("");
        details.push("⚠️ 高成本 / 长时间操作提示：");
        details.push(`- 预估分段数：${estSeg} 段（每段约 300 秒）`);
        details.push("- 转录模型：MiMo V2.5（语音识别 + 结构化提炼）");
        details.push(`- 长${isVideo ? "视频" : "音频"}处理预计耗时较长，请耐心等待`);
        details.push("- 处理期间请勿重复操作，完成后会收到通知");
        if (sizeMB > 500) {
          details.push("- 文件超过 500 MB，建议在网络稳定、有充裕时间时处理");
        }
      } else {
        details.push(`- 预估分段数：${estSeg} 段`);
        details.push(`- 短${isVideo ? "视频" : "音频"}，预计较快完成转录`);
      }
      details.push("");
      details.push("转录完成后将在当前文件夹的 02-转录文本 / 子目录生成结果。");

      setPendingConfirmation({
        title: isLong ? "上传并转录音视频（高成本操作）" : "上传并转录音视频",
        detail: details.join("\\n"),
        confirmLabel: "确认转录",
        tone: isLong ? "danger" : "warning",
        onConfirm: async () => {
          const folderPath = activeMeetingFolderPath;
          setNotice("正在转录音视频…");
          setRefreshingKnowledge(true);
          setError(null);
          try {
            const resp = await transcribeMeetingMedia(apiOptions, workspaceId!, folderPath, file);
            if (resp.agent_run) setLatestAgentRun(resp.agent_run);
            const notices: string[] = [];
            if (resp.transcription_status === "failed") {
              notices.push("转录失败 — 可点击「重试转录」再次尝试");
            } else if (resp.transcription_status === "partial") {
              notices.push(`部分转录完成（${resp.segment_count}段）— 可重试失败片段`);
            } else {
              notices.push(`转录完成（${resp.segment_count}段）`);
            }
            if (resp.warnings.length > 0) {
              notices.push(`${resp.warnings.length} 条警告`);
            }
            if (resp.token_cost > 0) {
              notices.push(`token：${resp.token_cost}`);
            }
            niceSaveSummary(resp.transcript_latest_path, resp.transcription_status);
            setNotice(notices.join("，"));
            await refresh();
          } catch (txErr: unknown) {
            setError(txErr instanceof Error ? txErr.message : "转录失败");
          } finally {
            setRefreshingKnowledge(false);
          }
        },
      });
    };
    input.click();
  }


  return {
    detectedSpeakers,
    handleGenerateMinutes,
    handleIngestMeeting,
    handleMediaTranscribe,
    handleMeetingFolderCreate,
    handleMeetingTranscriptSave,
    handleOpenSpeakerMap,
    handleRetryMeeting,
    handleSaveSpeakerMap,
    handleSaveTermCorrections,
    handleTranscriptFileSelect,
    meetingFolderForm,
    meetingTranscriptForm,
    openMeetingFolderForm,
    openMeetingTranscriptForm,
    setMeetingFolderForm,
    setMeetingTranscriptForm,
    setSpeakerMapNames,
    setSpeakerMapOpen,
    setTermCorrections,
    setTermCorrectionsOpen,
    setTermEditCorrected,
    setTermEditOriginal,
    speakerMapLoading,
    speakerMapNames,
    speakerMapOpen,
    termCorrections,
    termCorrectionsBusy,
    termCorrectionsOpen,
    termEditCorrected,
    termEditOriginal,
  };
}
