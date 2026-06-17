import type { GeneratedFileResponse } from "../../shared/api/types";
import {
  buildEditedEmailDraftEml,
  buildMailtoUrl,
  editableEmailDraft,
  editedEmailDraftFilename,
  emailDraftBodyForCopy,
  type EditableEmailDraft,
} from "./emailDraft";

type CopyText = (text: string, preserveFormatting: boolean) => Promise<void>;

export function useGeneratedEmailDraftActions(copyText: CopyText) {
  async function handleCopyGeneratedEmailBody(file: GeneratedFileResponse) {
    const body = emailDraftBodyForCopy(editableEmailDraft(file));
    if (!body.trim()) {
      throw new Error("邮件正文为空");
    }
    await copyText(body, false);
  }

  async function handleCopyEditableEmailDraft(draft: EditableEmailDraft) {
    const body = emailDraftBodyForCopy(draft);
    if (!body.trim()) {
      throw new Error("邮件正文为空");
    }
    await copyText(body, false);
  }

  function handleOpenEditableEmailDraft(draft: EditableEmailDraft) {
    window.location.href = buildMailtoUrl(draft);
  }

  function handleOpenGeneratedEmailClient(file: GeneratedFileResponse) {
    handleOpenEditableEmailDraft(editableEmailDraft(file));
  }

  function handleDownloadEditableEmailDraft(file: GeneratedFileResponse, draft: EditableEmailDraft) {
    const blob = new Blob([buildEditedEmailDraftEml(draft)], {
      type: "message/rfc822;charset=utf-8",
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = editedEmailDraftFilename(file, draft);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }

  return {
    handleCopyEditableEmailDraft,
    handleCopyGeneratedEmailBody,
    handleDownloadEditableEmailDraft,
    handleOpenEditableEmailDraft,
    handleOpenGeneratedEmailClient,
  };
}
