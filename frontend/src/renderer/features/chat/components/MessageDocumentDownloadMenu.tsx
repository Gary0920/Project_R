import { useEffect, useRef, useState } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import { DownloadIcon } from "../../../shared/icons/LineIcons";
import {
  downloadBlob,
  exportDocumentContent,
  inferDocumentTitle,
  type DocumentExportFormat,
} from "../documentExport";

type MessageDocumentDownloadMenuProps = {
  apiOptions: ApiClientOptions;
  content: string;
  disabled?: boolean;
  title?: string;
};

const FORMAT_OPTIONS: Array<{
  format: DocumentExportFormat;
  label: string;
  extension: string;
  badge: string;
  badgeClassName: string;
}> = [
  {
    format: "pdf",
    label: "PDF 文档",
    extension: ".pdf",
    badge: "PDF",
    badgeClassName: "is-pdf",
  },
  {
    format: "docx",
    label: "Microsoft Word",
    extension: ".docx",
    badge: "W",
    badgeClassName: "is-docx",
  },
];

export function MessageDocumentDownloadMenu({
  apiOptions,
  content,
  disabled = false,
  title,
}: MessageDocumentDownloadMenuProps) {
  const [open, setOpen] = useState(false);
  const [busyFormat, setBusyFormat] = useState<DocumentExportFormat | null>(null);
  const [error, setError] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  async function handleExport(format: DocumentExportFormat) {
    if (busyFormat) return;
    setBusyFormat(format);
    setError("");
    try {
      const result = await exportDocumentContent(apiOptions, {
        content,
        title: title || inferDocumentTitle(content),
        format,
      });
      downloadBlob(result.blob, result.filename);
      setOpen(false);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "下载失败");
    } finally {
      setBusyFormat(null);
    }
  }

  return (
    <div className="message-document-download" ref={rootRef}>
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="下载文档"
        className={`message-document-tool-btn ${open ? "is-active" : ""}`}
        disabled={disabled || Boolean(busyFormat)}
        onClick={() => setOpen((value) => !value)}
        title="下载"
        type="button"
      >
        <DownloadIcon />
      </button>
      {open ? (
        <div className="message-document-download-menu" role="menu" aria-label="下载格式">
          <div className="message-document-download-menu-title">下载</div>
          {FORMAT_OPTIONS.map((option) => (
            <button
              className="message-document-download-option"
              disabled={Boolean(busyFormat)}
              key={option.format}
              onClick={() => void handleExport(option.format)}
              role="menuitem"
              type="button"
            >
              <span aria-hidden className={`message-document-download-badge ${option.badgeClassName}`}>
                {option.badge}
              </span>
              <span className="message-document-download-label">{option.label}</span>
              <span className="message-document-download-ext">{option.extension}</span>
              {busyFormat === option.format ? <span className="message-document-download-busy">导出中</span> : null}
            </button>
          ))}
          {error ? <div className="message-document-download-error">{error}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
