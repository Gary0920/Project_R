import { ClipboardEvent, DragEvent, useEffect, useRef, useState, type RefObject } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import type {
  ChatSessionResponse,
  SessionAttachmentResponse,
  WorkspaceFileItemResponse,
} from "../../../shared/api/types";
import {
  createSessionAttachment,
  deleteSessionAttachment,
  uploadSessionAttachmentFile,
} from "../api";
import {
  SESSION_ATTACHMENT_MAX_BYTES,
  fileFromPrivateWorkspacePayload,
  filesFromClipboard,
  getAttachmentKind,
  hasFileTransfer,
  hashFileSha256,
  isLocalPrivatePendingAttachment,
  isUploadedPendingAttachment,
  makeLocalAttachmentId,
  pendingAttachmentKey,
  readTextAttachmentExcerpt,
  type AttachmentAuthorizationStatus,
  type AttachmentInputSource,
  type PendingSessionAttachment,
} from "../attachments";
import { fetchWorkspaceFileBlob } from "../../workspace/api";

type SplitPaneKey = "left" | "right";

type UseChatAttachmentsOptions = {
  activeSessionId: number | null;
  activeSplitPane: SplitPaneKey;
  activeWorkspaceId: number | null;
  activeWorkspaceKind?: string | null;
  apiOptions: ApiClientOptions;
  createSessionFromInput: (
    content?: string,
    openInNewTab?: boolean,
    promptIdForNewSession?: string | null,
    paneForNewSession?: SplitPaneKey,
  ) => Promise<ChatSessionResponse>;
  focusComposerRef: RefObject<HTMLTextAreaElement | null>;
  mode: string;
  sessions: ChatSessionResponse[];
  setActiveSplitPane: (pane: SplitPaneKey) => void;
  setError: (error: string | null) => void;
  activateConversationPane: (pane: SplitPaneKey, sessionId: number | null) => void;
};

export function useChatAttachments({
  activeSessionId,
  activeSplitPane,
  activeWorkspaceId,
  activeWorkspaceKind,
  apiOptions,
  createSessionFromInput,
  focusComposerRef,
  mode,
  sessions,
  setActiveSplitPane,
  setError,
  activateConversationPane,
}: UseChatAttachmentsOptions) {
  const [pendingAttachments, setPendingAttachments] = useState<PendingSessionAttachment[]>([]);
  const [isUploadingAttachments, setIsUploadingAttachments] = useState(false);
  const [attachmentDragTargetPane, setAttachmentDragTargetPane] = useState<SplitPaneKey | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pendingAttachmentPreviewsRef = useRef<Set<string>>(new Set());
  const previousWorkspaceIdRef = useRef<number | null | undefined>(undefined);

  async function makeLocalPendingAttachment(
    file: File,
    source: AttachmentInputSource,
    privateWorkspaceRecord?: PrivateWorkspaceFilePayload,
  ): Promise<PendingSessionAttachment> {
    const kind = getAttachmentKind(file.name, file.type || "");
    const localId = privateWorkspaceRecord?.id ?? makeLocalAttachmentId();
    const sha256 = privateWorkspaceRecord?.sha256 ?? await hashFileSha256(file);
    const createdAt = new Date().toISOString();
    const isPrivateWorkspaceFile = Boolean(privateWorkspaceRecord);
    const authorizationStatus: AttachmentAuthorizationStatus =
      isPrivateWorkspaceFile && privateWorkspaceRecord?.lastAuthorizationStatus !== "authorized"
        ? "pending"
        : "authorized";
    let previewUrl: string | undefined;
    if (kind === "image") {
      previewUrl = URL.createObjectURL(file);
      pendingAttachmentPreviewsRef.current.add(previewUrl);
    }
    return {
      id: -Date.now(),
      local_id: localId,
      session_id: null,
      message_id: null,
      original_name: file.name,
      content_type: file.type || "application/octet-stream",
      size: file.size,
      created_at: createdAt,
      kind,
      previewUrl,
      file,
      sha256,
      relative_path: privateWorkspaceRecord?.relativePath ?? null,
      private_workspace_file_id: privateWorkspaceRecord?.id ?? null,
      preprocess: privateWorkspaceRecord?.preprocess ?? null,
      source_scope: isPrivateWorkspaceFile ? "local_private" : "session_upload",
      source_label: isPrivateWorkspaceFile ? "本机选择" : "会话临时上传",
      authorization_status: authorizationStatus,
      input_source: source,
    };
  }

  function makeUploadedPendingAttachment(
    attachment: SessionAttachmentResponse,
    file: File,
    source?: PendingSessionAttachment,
  ): PendingSessionAttachment {
    const kind = getAttachmentKind(attachment.original_name || file.name, attachment.content_type || file.type);
    return {
      ...attachment,
      local_id: source?.local_id ?? `server-${attachment.id}`,
      kind,
      previewUrl: source?.previewUrl,
      sha256: source?.sha256 ?? null,
      relative_path: source?.relative_path ?? null,
      private_workspace_file_id: source?.private_workspace_file_id ?? null,
      preprocess: source?.preprocess ?? null,
      source_scope: source?.private_workspace_file_id ? "local_private" : "session_upload",
      source_label: source?.source_label ?? (source?.private_workspace_file_id ? "本机选择" : "会话临时上传"),
      authorization_status: "uploaded",
      input_source: source?.input_source ?? "picker",
    };
  }

  function revokeAttachmentPreviews(attachments: PendingSessionAttachment[]) {
    for (const attachment of attachments) {
      if (!attachment.previewUrl) continue;
      URL.revokeObjectURL(attachment.previewUrl);
      pendingAttachmentPreviewsRef.current.delete(attachment.previewUrl);
    }
  }

  function revokeAllAttachmentPreviews() {
    for (const previewUrl of pendingAttachmentPreviewsRef.current) {
      URL.revokeObjectURL(previewUrl);
    }
    pendingAttachmentPreviewsRef.current.clear();
  }

  async function resolveAttachmentSession(target?: { sessionId?: number | null; pane?: SplitPaneKey }) {
    if (target?.pane) {
      setActiveSplitPane(target.pane);
    }
    if (target?.sessionId) {
      const targetSession = sessions.find((item) => item.id === target.sessionId);
      if (targetSession) {
        if (target.pane) activateConversationPane(target.pane, targetSession.id);
        return targetSession;
      }
    }
    if (activeSessionId) {
      const currentSession = sessions.find((item) => item.id === activeSessionId);
      if (currentSession) return currentSession;
    }
    return createSessionFromInput("附件会话", true, null, target?.pane ?? activeSplitPane);
  }

  async function handleSelectAttachmentFiles(
    inputFiles: FileList | File[] | null,
    source: AttachmentInputSource = "picker",
    target?: { sessionId?: number | null; pane?: SplitPaneKey },
  ) {
    const files = Array.from(inputFiles ?? []).filter((file) => file.size > 0);
    if (!files.length) return;
    setError(null);
    setIsUploadingAttachments(true);
    try {
      const tooLarge = files.find((file) => file.size > SESSION_ATTACHMENT_MAX_BYTES);
      if (tooLarge) {
        throw new Error(`${tooLarge.name} 超过 20MB，请改用当前工作区文件管理上传。`);
      }
      if (target?.pane) {
        setActiveSplitPane(target.pane);
        activateConversationPane(target.pane, target.sessionId ?? null);
      }
      const localAttachments = await Promise.all(files.map((file) => makeLocalPendingAttachment(file, source)));
      setPendingAttachments((current) => [...current, ...localAttachments]);
      if (source !== "picker") {
        window.requestAnimationFrame(() => focusComposerRef.current?.focus());
      }
    } catch (uploadError: unknown) {
      setError(uploadError instanceof Error ? uploadError.message : "附件上传失败，请稍后重试。");
    } finally {
      setIsUploadingAttachments(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleReferenceWorkspaceFile(item: WorkspaceFileItemResponse) {
    if (!activeWorkspaceId || item.type === "directory") return;
    setError(null);
    setIsUploadingAttachments(true);
    try {
      const blob = await fetchWorkspaceFileBlob(apiOptions, activeWorkspaceId, item.path);
      if (blob.size > SESSION_ATTACHMENT_MAX_BYTES) {
        throw new Error(`${item.name} 超过 20MB，暂不支持作为本轮引用附件发送。`);
      }
      const file = new File([blob], item.name, { type: blob.type || "application/octet-stream" });
      const attachment = await makeLocalPendingAttachment(file, "workspace_reference");
      setPendingAttachments((current) => [
        ...current,
        {
          ...attachment,
          relative_path: item.path,
          source_label: activeWorkspaceKind === "customer" ? "CRM 文件引用" : "项目资料引用",
        },
      ]);
      window.requestAnimationFrame(() => focusComposerRef.current?.focus());
    } catch (referenceError: unknown) {
      setError(referenceError instanceof Error ? referenceError.message : "引用文件失败，请稍后重试。");
    } finally {
      setIsUploadingAttachments(false);
    }
  }

  async function handleChoosePrivateWorkspaceFiles() {
    if (!window.projectR?.privateWorkspace) {
      setError("本机文件选择仅在桌面客户端可用；当前可用附件按钮作为会话临时上传处理。");
      return;
    }
    setError(null);
    setIsUploadingAttachments(true);
    try {
      const payloads = await window.projectR.privateWorkspace.chooseFiles();
      if (!payloads.length) return;
      const tooLarge = payloads.find((file) => file.size > SESSION_ATTACHMENT_MAX_BYTES);
      if (tooLarge) {
        throw new Error(`${tooLarge.fileName} 超过 20MB，请改用当前工作区文件管理上传。`);
      }
      const attachments = await Promise.all(payloads.map((payload) => {
        const file = fileFromPrivateWorkspacePayload(payload);
        return makeLocalPendingAttachment(file, "private_workspace", payload);
      }));
      setPendingAttachments((current) => [...current, ...attachments]);
      window.requestAnimationFrame(() => focusComposerRef.current?.focus());
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "本机文件读取失败。");
    } finally {
      setIsUploadingAttachments(false);
    }
  }

  async function handleRemovePendingAttachment(attachment: PendingSessionAttachment) {
    if (isUploadedPendingAttachment(attachment)) {
      try {
        await deleteSessionAttachment(apiOptions, attachment.session_id, attachment.id);
      } catch {
        // Ignore stale attachment cleanup errors in the composer.
      }
    }
    revokeAttachmentPreviews([attachment]);
    const key = pendingAttachmentKey(attachment);
    setPendingAttachments((current) => current.filter((item) => pendingAttachmentKey(item) !== key));
  }

  function authorizeLocalPrivateAttachments() {
    const privateWorkspaceIds = pendingAttachments
      .map((attachment) => attachment.private_workspace_file_id)
      .filter((id): id is string => Boolean(id));
    if (privateWorkspaceIds.length) {
      window.projectR?.privateWorkspace?.setAuthorization({ ids: privateWorkspaceIds, status: "authorized" }).catch(() => {});
    }
    setPendingAttachments((current) =>
      current.map((attachment) =>
        isLocalPrivatePendingAttachment(attachment)
          ? { ...attachment, authorization_status: "authorized" }
          : attachment,
      ),
    );
    window.requestAnimationFrame(() => focusComposerRef.current?.focus());
  }

  async function uploadPendingAttachmentForSend(attachment: PendingSessionAttachment, sessionId: number) {
    if (isUploadedPendingAttachment(attachment)) {
      return attachment;
    }
    if (!attachment.file) {
      throw new Error(`本地附件已失效，请重新选择：${attachment.original_name}`);
    }
    let uploaded: PendingSessionAttachment;
    if (mode === "chat" && (attachment.kind === "text" || (attachment.kind === "pdf" && attachment.preprocess?.excerpt))) {
      const excerpt = attachment.preprocess?.excerpt ?? await readTextAttachmentExcerpt(attachment.file);
      const response = await createSessionAttachment(apiOptions, sessionId, {
        filename: attachment.original_name,
        content: excerpt || `[本机选择文件为空或无法读取：${attachment.original_name}]`,
        content_type: "text/plain",
        source_scope: attachment.private_workspace_file_id ? "local_private" : "session_upload",
        source_label: attachment.private_workspace_file_id ? "本机选择" : "会话临时上传",
        authorization_status: "uploaded",
      });
      uploaded = makeUploadedPendingAttachment(response, attachment.file, attachment);
    } else {
      const response = await uploadSessionAttachmentFile(apiOptions, sessionId, attachment.file, {
        source_scope: attachment.private_workspace_file_id ? "local_private" : "session_upload",
        source_label: attachment.private_workspace_file_id ? "本机选择" : "会话临时上传",
        authorization_status: "uploaded",
      });
      uploaded = makeUploadedPendingAttachment(response, attachment.file, attachment);
    }
    if (attachment.private_workspace_file_id) {
      window.projectR?.privateWorkspace?.setAuthorization({ ids: [attachment.private_workspace_file_id], status: "uploaded" }).catch(() => {});
    }
    return uploaded;
  }

  function handleComposerPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const files = filesFromClipboard(event.clipboardData);
    if (!files.length) return;
    event.preventDefault();
    void handleSelectAttachmentFiles(files, "paste");
  }

  function handleAttachmentDragEnter(event: DragEvent<HTMLDivElement>, pane: SplitPaneKey) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    setAttachmentDragTargetPane(pane);
  }

  function handleAttachmentDragOver(event: DragEvent<HTMLDivElement>, pane: SplitPaneKey) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setAttachmentDragTargetPane(pane);
  }

  function handleAttachmentDragLeave(event: DragEvent<HTMLDivElement>, pane: SplitPaneKey) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    const currentTarget = event.currentTarget;
    const relatedTarget = event.relatedTarget;
    if (relatedTarget instanceof Node && currentTarget.contains(relatedTarget)) return;
    if (attachmentDragTargetPane === pane) {
      setAttachmentDragTargetPane(null);
    }
  }

  function handleAttachmentDrop(
    event: DragEvent<HTMLDivElement>,
    pane: SplitPaneKey,
    paneSessionId: number | null,
  ) {
    if (!hasFileTransfer(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    setAttachmentDragTargetPane(null);
    activateConversationPane(pane, paneSessionId);
    void handleSelectAttachmentFiles(Array.from(event.dataTransfer.files), "drop", { sessionId: paneSessionId, pane });
  }

  useEffect(() => {
    setPendingAttachments((current) => {
      const next = current.filter((attachment) => attachment.session_id === activeSessionId);
      if (next.length === current.length) return current;
      revokeAttachmentPreviews(current.filter((attachment) => attachment.session_id !== activeSessionId));
      return next;
    });
  }, [activeSessionId]);

  useEffect(() => {
    const previousWorkspaceId = previousWorkspaceIdRef.current;
    previousWorkspaceIdRef.current = activeWorkspaceId;
    if (previousWorkspaceId === undefined || previousWorkspaceId === activeWorkspaceId) return;
    setPendingAttachments((current) => {
      if (!current.length) return current;
      revokeAttachmentPreviews(current);
      return [];
    });
  }, [activeWorkspaceId]);

  useEffect(() => {
    return () => revokeAllAttachmentPreviews();
  }, []);

  return {
    attachmentDragTargetPane,
    authorizeLocalPrivateAttachments,
    fileInputRef,
    handleAttachmentDragEnter,
    handleAttachmentDragLeave,
    handleAttachmentDragOver,
    handleAttachmentDrop,
    handleChoosePrivateWorkspaceFiles,
    handleComposerPaste,
    handleReferenceWorkspaceFile,
    handleRemovePendingAttachment,
    handleSelectAttachmentFiles,
    isUploadingAttachments,
    pendingAttachments,
    resolveAttachmentSession,
    revokeAttachmentPreviews,
    setIsUploadingAttachments,
    setPendingAttachments,
    uploadPendingAttachmentForSend,
  };
}
