import { useState } from "react";

import type { GeneratedFileResponse, WorkspaceResponse } from "../../../shared/api/types";
import { CheckIcon, NoteIcon, WorkspaceIcon } from "../../../shared/icons/LineIcons";

type SaveResult = {
  path: string;
};

export type GeneratedFileCardProps = {
  file: GeneratedFileResponse;
  workspace?: WorkspaceResponse | null;
  onDownload: (file: GeneratedFileResponse) => void;
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
  return "已生成文件";
}

function workspaceSaveLabel(workspace: WorkspaceResponse) {
  if (workspace.workspace_kind === "customer") return "保存到 CRM";
  return "保存到项目";
}

export function GeneratedFileCard({
  file,
  workspace,
  onDownload,
  onSaveToWorkspace,
}: GeneratedFileCardProps) {
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [savedPath, setSavedPath] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const canSaveToWorkspace = Boolean(workspace && workspace.workspace_kind !== "user" && onSaveToWorkspace);

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

  return (
    <div className={`message-file-card is-${saveStatus}`}>
      <div className="message-file-card-main">
        <span className="message-file-icon"><NoteIcon /></span>
        <div>
          <strong>{file.filename}</strong>
          <span>{generatedFileKindLabel(file)}</span>
        </div>
      </div>
      <div className="message-file-actions">
        <button
          className="message-file-download"
          onClick={() => onDownload(file)}
          type="button"
        >
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
