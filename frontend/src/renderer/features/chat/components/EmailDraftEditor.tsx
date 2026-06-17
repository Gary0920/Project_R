import { useEffect, useState } from "react";

import type { GeneratedFileResponse } from "../../../shared/api/types";
import { CopyIcon, XmarkIcon } from "../../../shared/icons/LineIcons";
import { editableEmailDraft, type EditableEmailDraft } from "../emailDraft";

export type EmailDraftEditorProps = {
  file: GeneratedFileResponse;
  onClose: () => void;
  onCopy: (draft: EditableEmailDraft) => Promise<void>;
  onDownload: (file: GeneratedFileResponse, draft: EditableEmailDraft) => void;
  onOpenEmailClient: (draft: EditableEmailDraft) => void;
};

export function EmailDraftEditor({
  file,
  onClose,
  onCopy,
  onDownload,
  onOpenEmailClient,
}: EmailDraftEditorProps) {
  const [draft, setDraft] = useState<EditableEmailDraft>(() => editableEmailDraft(file));
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    setDraft(editableEmailDraft(file));
    setCopyStatus("idle");
  }, [file.id]);

  async function handleCopy() {
    try {
      await onCopy(draft);
      setCopyStatus("copied");
      window.setTimeout(() => setCopyStatus("idle"), 1600);
    } catch {
      setCopyStatus("failed");
    }
  }

  return (
    <div className="email-draft-editor-backdrop" role="presentation">
      <section className="email-draft-editor" aria-modal="true" role="dialog">
        <header className="email-draft-editor-header">
          <div>
            <strong>邮件草稿</strong>
            <span>检查并调整后再复制、打开邮件客户端或下载编辑后的 .eml。</span>
          </div>
          <button className="email-draft-editor-close" onClick={onClose} title="关闭" type="button">
            <XmarkIcon />
          </button>
        </header>
        <div className="email-draft-editor-grid">
          <label>
            <span>To</span>
            <input value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} />
          </label>
          <label>
            <span>Cc</span>
            <input value={draft.cc} onChange={(event) => setDraft({ ...draft, cc: event.target.value })} />
          </label>
          <label className="email-draft-editor-full">
            <span>Subject</span>
            <input value={draft.subject} onChange={(event) => setDraft({ ...draft, subject: event.target.value })} />
          </label>
          <label className="email-draft-editor-full">
            <span>Body</span>
            <textarea value={draft.body} onChange={(event) => setDraft({ ...draft, body: event.target.value })} />
          </label>
        </div>
        <footer className="email-draft-editor-actions">
          <button className="btn-secondary" onClick={() => onDownload(file, draft)} type="button">下载编辑后 .eml</button>
          <button className="btn-secondary" onClick={() => void handleCopy()} type="button">
            <CopyIcon />
            {copyStatus === "copied" ? "已复制" : copyStatus === "failed" ? "复制失败" : "复制正文"}
          </button>
          <button className="btn-primary" onClick={() => onOpenEmailClient(draft)} type="button">打开邮件客户端</button>
        </footer>
      </section>
    </div>
  );
}
