import type { WorkspaceFileItemResponse } from "../../shared/api/types";
import { MEETING_ROOT_PATH, MEETING_WORKFLOW_DIRS } from "./workspaceFilePanelUtils";

const MEETING_AUDIO_EXTENSIONS = new Set(["mp3", "wav", "m4a", "ogg", "flac", "mp4", "mov", "avi", "wmv", "mkv", "webm"]);
const MEETING_TRANSCRIPT_EXTENSIONS = new Set(["txt", "md", "markdown", "docx"]);

export function isMeetingAudioFile(name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return MEETING_AUDIO_EXTENSIONS.has(ext);
}

export function isMeetingTranscriptFile(name: string): boolean {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return MEETING_TRANSCRIPT_EXTENSIONS.has(ext);
}

export function isMeetingTranscriptSourceFile(item: WorkspaceFileItemResponse): boolean {
  if (!isMeetingTranscriptFile(item.name)) return false;
  const lowerPath = item.path.toLowerCase();
  const lowerName = item.name.toLowerCase();
  return lowerPath.includes("/02-转录文本/") || lowerName.startsWith("transcript");
}

export function isInMeetingWorkflowPath(filePath: string): boolean {
  return filePath === MEETING_ROOT_PATH || filePath.startsWith(`${MEETING_ROOT_PATH}/`);
}

export function isMeetingWorkflowSubdirName(name: string): boolean {
  return MEETING_WORKFLOW_DIRS.includes(name);
}

export function isMeetingFolderPath(path: string): boolean {
  const parts = path.split("/");
  return parts[0] === MEETING_ROOT_PATH;
}

export function inferMeetingFolder(filePath: string): string | null {
  const parts = filePath.split("/");
  if (parts[0] !== MEETING_ROOT_PATH) return null;
  return MEETING_ROOT_PATH;
}
