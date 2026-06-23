import { useState } from "react";

import type { GeneratedFileResponse, WorkspaceResponse } from "../../../shared/api/types";
import { CheckIcon, CopyIcon, NoteIcon, WorkspaceIcon } from "../../../shared/icons/LineIcons";
import { emailDraftSummary, isEmailDraftFile } from "../emailDraft";

type SaveResult = {
  path: string;
};

export type GeneratedFileCardProps = {
  file: GeneratedFileResponse;
  workspace?: WorkspaceResponse | null;
  variant?: "card" | "document";
  onDownload: (file: GeneratedFileResponse) => void;
  onCopyEmailBody?: (file: GeneratedFileResponse) => Promise<void>;
  onEditEmailDraft?: (file: GeneratedFileResponse) => void;
  onOpenEmailClient?: (file: GeneratedFileResponse) => void;
  onSaveToWorkspace?: (file: GeneratedFileResponse) => Promise<SaveResult>;
};

function generatedFileKindLabel(file: GeneratedFileResponse) {
  const mime = (file.mime_type || "").toLowerCase();
  const name = (file.filename || "").toLowerCase();
  if (mime.includes("word") || name.endsWith(".docx")) return "已生成 Word 文档";
  if (mime.includes("markdown") || name.endsWith(".md") || name.endsWith(".markdown")) return "已生成 Markdown 文件";
  if (mime.includes("text/plain") || name.endsWith(".txt")) return "已生成纯文本文件";
  if (mime.includes("spreadsheet") || name.endsWith(".xlsx")) return "已生成 Excel 文件";
  if (mime.includes("presentation") || name.endsWith(".pptx")) return "已生成演示文稿";
  if (mime.includes("pdf") || name.endsWith(".pdf")) return "已生成 PDF 文件";
  if (mime.includes("message/rfc822") || name.endsWith(".eml")) return "已生成邮件草稿";
  return "已生成文件";
}

function workspaceSaveLabel(workspace: WorkspaceResponse) {
  if (workspace.workspace_kind === "customer") return "保存到 CRM";
  return "保存到项目";
}

export function GeneratedFileCard({
  file,
  workspace,
  variant = "document",
  onDownload,
  onCopyEmailBody,
  onEditEmailDraft,
  onOpenEmailClient,
  onSaveToWorkspace,
}: GeneratedFileCardProps) {
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const [savedPath, setSavedPath] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const canSaveToWorkspace = Boolean(workspace && workspace.workspace_kind !== "user" && onSaveToWorkspace);
  const isEmailDraft = isEmailDraftFile(file);
  const summary = isEmailDraft ? emailDraftSummary(file) : null;

  async function handleSave() {
    if (!onSaveToWorkspace || !workspace || saveStatus === "saving") return;
    setSaveStatus("saving");
    setErrorMessage("");
    try {
      const result = await onSaveToWorkspace(file);
      setSavedPath(result.path);
      setSaveStatus("saved");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "保存失败");
      setSaveStatus("failed");
    }
  }

  async function handleCopyEmailBody() {
    if (!onCopyEmailBody) return;
    setCopyStatus("idle");
    try {
      await onCopyEmailBody(file);
      setCopyStatus("copied");
      window.setTimeout(() => setCopyStatus("idle"), 1600);
    } catch {
      setCopyStatus("failed");
    }
  }

  const actionButtons = (
    <>
      {isEmailDraft && onEditEmailDraft ? (
        <button className="ghost-button message-deliverable-action" onClick={() => onEditEmailDraft(file)} type="button">
          查看/编辑草稿
        </button>
      ) : null}
      {isEmailDraft && onCopyEmailBody ? (
        <button
          className={`ghost-button message-deliverable-action ${copyStatus !== "idle" ? `is-${copyStatus}` : ""}`}
          onClick={() => void handleCopyEmailBody()}
          type="button"
        >
          {copyStatus === "copied" ? <CheckIcon /> : <CopyIcon />}
          {copyStatus === "copied" ? "已复制" : copyStatus === "failed" ? "复制失败" : "复制正文"}
        </button>
      ) : null}
      {isEmailDraft && onOpenEmailClient ? (
        <button className="ghost-button message-deliverable-action" onClick={() => onOpenEmailClient(file)} type="button">
          打开邮件
        </button>
      ) : null}
      <button className="ghost-button message-deliverable-action" onClick={() => onDownload(file)} type="button">
        下载
      </button>
      {canSaveToWorkspace && workspace ? (
        <button
          className="ghost-button message-deliverable-action"
          disabled={saveStatus === "saving" || saveStatus === "saved"}
          onClick={() => void handleSave()}
          type="button"
        >
          {saveStatus === "saved" ? <CheckIcon /> : <WorkspaceIcon />}
          {saveStatus === "saving" ? "保存中" : saveStatus === "saved" ? "已保存" : workspaceSaveLabel(workspace)}
        </button>
      ) : null}
    </>
  );

  if (variant === "document") {
    return (
      <div className={`message-deliverable is-${saveStatus} ${isEmailDraft ? "is-email-draft" : ""}`}>
        {isEmailDraft && summary ? (
          <>
            {summary.subject ? <div className="message-deliverable-subject">{summary.subject}</div> : null}
            {summary.bodyPreview ? <div className="message-deliverable-body">{summary.bodyPreview}</div> : null}
          </>
        ) : (
          <div className="message-deliverable-body">
            <strong>{file.filename}</strong>
            <span>{generatedFileKindLabel(file)}</span>
          </div>
        )}
        <div className="message-deliverable-actions">{actionButtons}</div>
        {saveStatus === "saved" && savedPath ? (
          <div className="message-deliverable-status">已保存到 {savedPath}</div>
        ) : null}
        {saveStatus === "failed" && errorMessage ? (
          <div className="message-deliverable-status is-error">{errorMessage}</div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={`message-file-card is-${saveStatus} ${isEmailDraft ? "is-email-draft" : ""}`}>
      <div className="message-file-card-main">
        <span className="message-file-icon"><NoteIcon /></span>
        <div>
          <strong>{file.filename}</strong>
          <span>{summary?.subject ? `邮件草稿：${summary.subject}` : generatedFileKindLabel(file)}</span>
          {summary?.bodyPreview ? <small>{summary.bodyPreview}</small> : null}
        </div>
      </div>
      <div className="message-file-actions">
        {isEmailDraft && onEditEmailDraft ? (
          <button className="message-file-save" onClick={() => onEditEmailDraft(file)} type="button">
            查看/编辑草稿
          </button>
        ) : null}
        {isEmailDraft && onCopyEmailBody ? (
          <button
            className={`message-file-download ${copyStatus !== "idle" ? `is-${copyStatus}` : ""}`}
            onClick={() => void handleCopyEmailBody()}
            type="button"
          >
            {copyStatus === "copied" ? <CheckIcon /> : <CopyIcon />}
            {copyStatus === "copied" ? "已复制" : copyStatus === "failed" ? "复制失败" : "复制正文"}
          </button>
        ) : null}
        {isEmailDraft && onOpenEmailClient ? (
          <button className="message-file-download" onClick={() => onOpenEmailClient(file)} type="button">
            打开邮件
          </button>
        ) : null}
        <button className="message-file-download" onClick={() => onDownload(file)} type="button">
          下载
        </button>
        {canSaveToWorkspace && workspace ? (
          <button
            className="message-file-save"
            disabled={saveStatus === "saving" || saveStatus === "saved"}
            onClick={() => void handleSave()}
            type="button"
          >
            {saveStatus === "saved" ? <CheckIcon /> : <WorkspaceIcon />}
            {saveStatus === "saving" ? "保存中" : saveStatus === "saved" ? "已保存" : workspaceSaveLabel(workspace)}
          </button>
        ) : null}
      </div>
      {saveStatus === "saved" && savedPath ? (
        <div className="message-file-status">已保存到 {savedPath}</div>
      ) : null}
      {saveStatus === "failed" && errorMessage ? (
        <div className="message-file-status is-error">{errorMessage}</div>
      ) : null}
    </div>
  );
}
