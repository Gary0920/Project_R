import { useEffect, useState } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import type { SessionAttachmentResponse } from "../../../shared/api/types";
import { XmarkIcon } from "../../../shared/icons/LineIcons";
import { fetchSessionAttachmentBlob } from "../api";

type AttachmentKind = "image" | "pdf" | "text" | "file";

function getAttachmentKind(fileName: string, contentType: string): AttachmentKind {
  const lowerName = fileName.toLowerCase();
  const lowerType = contentType.toLowerCase();
  if (lowerType.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(lowerName)) return "image";
  if (lowerType.includes("pdf") || lowerName.endsWith(".pdf")) return "pdf";
  if (lowerType.startsWith("text/") || /\.(txt|md|csv|json|log)$/i.test(lowerName)) return "text";
  return "file";
}

function formatAttachmentSize(size: number) {
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function attachmentSourceLabel(attachment: { source_label?: string; source_scope?: string }) {
  if (attachment.source_label) return attachment.source_label;
  if (attachment.source_scope === "workspace") return "工作区文件";
  if (attachment.source_scope === "local_private") return "本机文件";
  return "会话附件";
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function isImageAttachmentResponse(attachment: SessionAttachmentResponse) {
  return (attachment.content_type || "").toLowerCase().startsWith("image/");
}

function attachmentKindLabel(attachment: SessionAttachmentResponse) {
  const kind = getAttachmentKind(attachment.original_name, attachment.content_type || "");
  if (kind === "image") return "IMG";
  if (kind === "pdf") return "PDF";
  if (kind === "text") return "TXT";
  return "FILE";
}

export function MessageAttachments({
  attachments,
  apiOptions,
}: {
  attachments?: SessionAttachmentResponse[];
  apiOptions: ApiClientOptions;
}) {
  const visibleAttachments = attachments ?? [];
  if (!visibleAttachments.length) return null;
  return (
    <div className={`message-attachments ${visibleAttachments.length === 1 ? "is-single" : ""}`}>
      {visibleAttachments.map((attachment) =>
        isImageAttachmentResponse(attachment) ? (
          <MessageAttachmentImage attachment={attachment} apiOptions={apiOptions} key={attachment.id} />
        ) : (
          <MessageAttachmentFile attachment={attachment} apiOptions={apiOptions} key={attachment.id} />
        ),
      )}
    </div>
  );
}

function MessageAttachmentImage({
  attachment,
  apiOptions,
}: {
  attachment: SessionAttachmentResponse;
  apiOptions: ApiClientOptions;
}) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setImageUrl(null);
    setLoadFailed(false);
    fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setLoadFailed(true);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [apiOptions.baseUrl, apiOptions.token, apiOptions.onUnauthorized, attachment.id, attachment.session_id]);

  useEffect(() => {
    if (!previewOpen) return;
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setPreviewOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [previewOpen]);

  return (
    <>
      <button
        className={`message-attachment-image ${loadFailed ? "is-failed" : ""}`}
        disabled={!imageUrl}
        onClick={() => imageUrl ? setPreviewOpen(true) : undefined}
        title={imageUrl ? `点击预览图片 · ${attachmentSourceLabel(attachment)}` : attachment.original_name}
        type="button"
      >
        {imageUrl ? (
          <>
            <img alt={attachment.original_name} src={imageUrl} />
            <span className="message-attachment-image-source">{attachmentSourceLabel(attachment)}</span>
          </>
        ) : (
          <span>{loadFailed ? "图片加载失败" : "图片加载中"}</span>
        )}
      </button>
      {previewOpen && imageUrl ? (
        <div className="attachment-lightbox-backdrop" onClick={() => setPreviewOpen(false)} role="presentation">
          <div className="attachment-lightbox" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <button className="attachment-lightbox-close" onClick={() => setPreviewOpen(false)} title="关闭预览" type="button">
              <XmarkIcon />
            </button>
            <img alt={attachment.original_name} src={imageUrl} />
            <div className="attachment-lightbox-footer">
              <span>{attachment.original_name} · {attachmentSourceLabel(attachment)}</span>
              <button
                onClick={() => void fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id)
                  .then((blob) => downloadBlob(blob, attachment.original_name))
                  .catch(() => {})}
                type="button"
              >
                下载
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function MessageAttachmentFile({
  attachment,
  apiOptions,
}: {
  attachment: SessionAttachmentResponse;
  apiOptions: ApiClientOptions;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const kind = getAttachmentKind(attachment.original_name, attachment.content_type || "");
  const canPreview = kind === "pdf" || kind === "text";
  const sourceLabel = attachmentSourceLabel(attachment);

  async function handleOpenAttachment() {
    setBusy(true);
    setFailed(false);
    try {
      const blob = await fetchSessionAttachmentBlob(apiOptions, attachment.session_id, attachment.id);
      if (canPreview) {
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank", "noopener,noreferrer");
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } else {
        downloadBlob(blob, attachment.original_name);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      className="message-attachment-file"
      disabled={busy}
      onClick={() => void handleOpenAttachment()}
      title={failed ? "附件打开失败" : canPreview ? "打开预览" : "下载附件"}
      type="button"
    >
      <span className={`message-attachment-file-kind is-${kind}`}>{attachmentKindLabel(attachment)}</span>
      <span className="message-attachment-file-main">
        <strong>{attachment.original_name}</strong>
        <small>{failed ? "打开失败" : `${sourceLabel} · ${formatAttachmentSize(attachment.size)} · ${canPreview ? "打开预览" : "下载"}`}</small>
      </span>
    </button>
  );
}
