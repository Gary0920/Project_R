import type { ApiClientOptions } from "../../../shared/api/client";
import { CheckIcon, CopyIcon, EditIcon, MaximizeIcon } from "../../../shared/icons/LineIcons";
import { MessageDocumentDownloadMenu } from "./MessageDocumentDownloadMenu";

type CopyState = "idle" | "copied" | "failed";

type MessageDocumentToolbarProps = {
  apiOptions: ApiClientOptions;
  content: string;
  copyState: CopyState;
  documentTitle: string;
  onCopy: () => void;
  onExpand: () => void;
};

export function MessageDocumentToolbar({
  apiOptions,
  content,
  copyState,
  documentTitle,
  onCopy,
  onExpand,
}: MessageDocumentToolbarProps) {
  return (
    <div className="message-document-toolbar">
      <div className="message-document-toolbar-left">
        <button
          aria-label="暂未接入编辑"
          className="message-document-edit-btn"
          disabled
          title="暂未接入编辑"
          type="button"
        >
          <EditIcon />
          <span>编辑</span>
        </button>
      </div>
      <div className="message-document-toolbar-actions" aria-label="文档块操作">
        <button
          aria-label={copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
          className={`message-document-tool-btn ${copyState !== "idle" ? `is-${copyState}` : ""}`}
          onClick={onCopy}
          title={copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制"}
          type="button"
        >
          {copyState === "copied" ? <CheckIcon /> : <CopyIcon />}
        </button>
        <MessageDocumentDownloadMenu
          apiOptions={apiOptions}
          content={content}
          title={documentTitle}
        />
        <button
          aria-label="展开阅读"
          className="message-document-tool-btn"
          onClick={onExpand}
          title="展开"
          type="button"
        >
          <MaximizeIcon />
        </button>
      </div>
    </div>
  );
}
