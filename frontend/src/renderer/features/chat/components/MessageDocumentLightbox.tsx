import { useEffect } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import { XmarkIcon } from "../../../shared/icons/LineIcons";
import { MessageDocumentToolbar } from "./MessageDocumentToolbar";

type CopyState = "idle" | "copied" | "failed";

type MessageDocumentLightboxProps = {
  apiOptions: ApiClientOptions;
  content: string;
  copyState: CopyState;
  documentTitle: string;
  onClose: () => void;
  onCopy: () => void;
};

export function MessageDocumentLightbox({
  apiOptions,
  content,
  copyState,
  documentTitle,
  onClose,
  onCopy,
}: MessageDocumentLightboxProps) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="message-document-lightbox-backdrop" onClick={onClose} role="presentation">
      <section
        aria-label="文档阅读"
        className="message-document-lightbox"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <button
          aria-label="关闭"
          className="message-document-lightbox-close"
          onClick={onClose}
          type="button"
        >
          <XmarkIcon />
        </button>
        <MessageDocumentToolbar
          apiOptions={apiOptions}
          content={content}
          copyState={copyState}
          documentTitle={documentTitle}
          onCopy={onCopy}
          onExpand={onClose}
        />
        <div className="message-document-lightbox-body">{content}</div>
      </section>
    </div>
  );
}
