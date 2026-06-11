import type { SessionAttachmentResponse } from "../../shared/api/types";

export type AttachmentInputSource = "picker" | "paste" | "drop" | "private_workspace" | "workspace_reference";
export type AttachmentSourceScope = "local_private" | "session_upload";
export type AttachmentAuthorizationStatus = "pending" | "authorized" | "uploaded";

export type PendingSessionAttachment = Omit<SessionAttachmentResponse, "session_id"> & {
  local_id: string;
  session_id: number | null;
  kind: "image" | "pdf" | "text" | "file";
  previewUrl?: string;
  file?: File;
  sha256?: string | null;
  relative_path?: string | null;
  private_workspace_file_id?: string | null;
  preprocess?: PrivateWorkspacePreprocessResult | null;
  source_scope: AttachmentSourceScope;
  source_label: string;
  authorization_status: AttachmentAuthorizationStatus;
  input_source: AttachmentInputSource;
};

export const SESSION_ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024;

const LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS = 12000;
const PASTED_IMAGE_EXTENSION_BY_TYPE: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/bmp": "bmp",
};

export function getAttachmentKind(fileName: string, contentType: string): PendingSessionAttachment["kind"] {
  const normalizedType = contentType.toLowerCase();
  const normalizedName = fileName.toLowerCase();
  if (normalizedType.startsWith("image/")) return "image";
  if (normalizedType === "application/pdf" || normalizedName.endsWith(".pdf")) return "pdf";
  if (normalizedType.startsWith("text/") || /\.(txt|md|markdown|csv|json|yaml|yml|log|html|css|js|ts|tsx|py)$/i.test(normalizedName)) {
    return "text";
  }
  return "file";
}

export function formatAttachmentSize(size: number) {
  if (size < 1024) return `${size}B`;
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)}KB`;
  return `${(size / 1024 / 1024).toFixed(1)}MB`;
}

export function makeLocalAttachmentId() {
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `local-${Date.now()}-${randomPart}`;
}

export function pendingAttachmentKey(attachment: PendingSessionAttachment) {
  return attachment.local_id || `server-${attachment.id}`;
}

export function isLocalPrivatePendingAttachment(attachment: PendingSessionAttachment) {
  return attachment.source_scope === "local_private";
}

export function isUploadedPendingAttachment(attachment: PendingSessionAttachment): attachment is PendingSessionAttachment & { session_id: number; id: number } {
  return attachment.authorization_status === "uploaded" && attachment.session_id !== null && attachment.id > 0;
}

export function attachmentSourceLabel(attachment: { source_label?: string; source_scope?: string }) {
  if (attachment.source_label) return attachment.source_label;
  if (attachment.source_scope === "local_private") return "本机选择";
  if (attachment.source_scope === "project") return "项目资料";
  if (attachment.source_scope === "company") return "公司知识库";
  return "会话临时上传";
}

export function pendingAttachmentStatusLabel(attachment: PendingSessionAttachment) {
  if (attachment.source_scope !== "local_private") {
    return attachment.authorization_status === "uploaded" ? "已附加" : "可直接发送";
  }
  return attachment.authorization_status === "authorized" ? "已确认" : "待确认";
}

export function pendingAttachmentSendFormLabel(attachment: PendingSessionAttachment, mode: string) {
  if (mode === "chat" && attachment.preprocess?.sendForm === "excerpt") return "发送摘录";
  if (mode === "chat" && attachment.kind === "text") return "发送摘录";
  if (mode === "chat" && attachment.kind === "pdf" && attachment.preprocess?.extractionStatus === "pdf_text_unavailable") return "上传 PDF 原文件";
  if (mode === "chat" && attachment.kind === "image") return "上传图片给模型";
  if (mode === "agent") return "上传临时文件";
  return "上传临时文件";
}

export function pendingAttachmentTargetLabel(mode: string) {
  return mode === "agent" ? "Agent 临时任务" : "Chat 会话";
}

export async function hashFileSha256(file: File) {
  if (!window.crypto?.subtle) return null;
  try {
    const digest = await window.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    return null;
  }
}

export async function readTextAttachmentExcerpt(file: File) {
  const text = await file.text();
  const normalized = text.trim();
  if (normalized.length <= LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS) return normalized;
  return `${normalized.slice(0, LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS)}\n\n[本机选择文件摘录已截断，仅发送前 ${LOCAL_TEXT_ATTACHMENT_EXCERPT_CHARS} 个字符。]`;
}

export function fileFromPrivateWorkspacePayload(payload: PrivateWorkspaceFilePayload) {
  const binary = atob(payload.base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new File([bytes], payload.fileName, {
    type: payload.contentType || "application/octet-stream",
    lastModified: new Date(payload.updatedAt).getTime() || Date.now(),
  });
}

function makePastedAttachmentName(file: File, index: number) {
  if (file.name && file.name !== "image.png") return file.name;
  const extension = PASTED_IMAGE_EXTENSION_BY_TYPE[file.type] ?? "png";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `pasted-image-${stamp}-${index + 1}.${extension}`;
}

function normalizePastedFile(file: File, index: number) {
  const name = makePastedAttachmentName(file, index);
  if (file.name === name) return file;
  return new File([file], name, { type: file.type || "application/octet-stream", lastModified: file.lastModified || Date.now() });
}

export function filesFromClipboard(data: DataTransfer) {
  const directFiles = Array.from(data.files ?? []);
  if (directFiles.length) {
    return directFiles.map(normalizePastedFile);
  }
  return Array.from(data.items ?? [])
    .filter((item) => item.kind === "file")
    .map((item, index) => {
      const file = item.getAsFile();
      return file ? normalizePastedFile(file, index) : null;
    })
    .filter((file): file is File => Boolean(file));
}

export function hasFileTransfer(data: DataTransfer | null) {
  if (!data) return false;
  return Array.from(data.types ?? []).includes("Files") || Array.from(data.items ?? []).some((item) => item.kind === "file");
}

export function isAudioVideoAttachment(attachment: PendingSessionAttachment) {
  const contentType = (attachment.content_type || "").toLowerCase();
  return contentType.startsWith("audio/") || contentType.startsWith("video/");
}

export function isAudioTranscriptionRequest(content: string) {
  return /录音转文字|音频转录|音频转文字|语音转文字|录音转录|转录成文字|转成文字|transcribe audio|audio transcription/i.test(content);
}
