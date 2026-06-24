import { useState } from "react";

import {
  CopyIcon,
  EditIcon,
  MoreIcon,
  NoteIcon,
  RefreshIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  TrashIcon,
} from "../../../shared/icons/LineIcons";
import type { ChatMessageVersionResponse } from "../../../shared/api/types";
import type { ChatMessage } from "../state";

export type MessageActionsProps = {
  copied: boolean;
  isBusy: boolean;
  message: ChatMessage;
  onActivateVersion: (message: ChatMessage, version: ChatMessageVersionResponse) => void;
  onCopy: (message: ChatMessage) => void;
  onDelete: (message: ChatMessage) => void;
  onFeedback: (message: ChatMessage, feedback: "like" | "dislike") => void;
  onQuote: (message: ChatMessage) => void;
  onRegenerate: (message: ChatMessage) => void;
  onStartEdit: (message: ChatMessage) => void;
};

export function MessageActions({
  copied,
  isBusy,
  message,
  onActivateVersion,
  onCopy,
  onDelete,
  onFeedback,
  onQuote,
  onRegenerate,
  onStartEdit,
}: MessageActionsProps) {
  const [moreOpen, setMoreOpen] = useState(false);
  const disabled = message.isOptimistic || isBusy;
  const versions = message.versions?.filter((version) => version.id > 0) ?? [];

  function closeAfter(action: () => void) {
    action();
    setMoreOpen(false);
  }

  return (
    <div className={`message-actions ${copied ? "has-copy-success" : ""}`}>
      <button
        className={`message-action-btn ${copied ? "is-copied" : ""}`}
        onClick={() => onCopy(message)}
        title={copied ? "已复制" : "复制"}
        type="button"
      >
        {copied ? <span className="message-action-check">✓</span> : <CopyIcon />}
      </button>
      {message.role === "assistant" ? (
        <>
          <button
            className={`message-action-btn ${message.feedback === "like" ? "is-active-feedback" : ""}`}
            disabled={disabled}
            onClick={() => onFeedback(message, "like")}
            title="喜欢"
            type="button"
          >
            <ThumbsUpIcon />
          </button>
          <button
            className={`message-action-btn ${message.feedback === "dislike" ? "is-active-feedback" : ""}`}
            disabled={disabled}
            onClick={() => onFeedback(message, "dislike")}
            title="不喜欢"
            type="button"
          >
            <ThumbsDownIcon />
          </button>
          <button
            className="message-action-btn"
            disabled={disabled}
            onClick={() => onRegenerate(message)}
            title="重新生成回答"
            type="button"
          >
            <RefreshIcon />
          </button>
        </>
      ) : null}
      <span className="message-more-wrap">
        <button
          aria-expanded={moreOpen}
          className="message-action-btn"
          disabled={message.isOptimistic}
          onClick={() => setMoreOpen((value) => !value)}
          title="更多操作"
          type="button"
        >
          <MoreIcon />
        </button>
        {moreOpen ? (
          <div className={`message-more-menu ${message.role === "assistant" && versions.length <= 1 ? "is-compact-icons" : ""}`}>
            <div className="message-more-icon-row">
              <button
                aria-label="引用"
                className="message-more-icon-btn"
                onClick={() => closeAfter(() => onQuote(message))}
                title="引用"
                type="button"
              >
                <NoteIcon />
              </button>
              <button
                aria-label="删除这一轮对话"
                className="message-more-icon-btn is-danger"
                disabled={disabled}
                onClick={() => closeAfter(() => onDelete(message))}
                title="删除这一轮对话"
                type="button"
              >
                <TrashIcon />
              </button>
            </div>
            {message.role === "user" ? (
              <button disabled={disabled} onClick={() => closeAfter(() => onStartEdit(message))} type="button">
                <EditIcon />
                <span>编辑并开启新分支</span>
              </button>
            ) : null}
            {versions.length > 1 ? (
              <div className="message-more-versions">
                <span>切换版本</span>
                {versions.map((version) => (
                  <button
                    className={version.active_version ? "is-active" : ""}
                    disabled={disabled || version.active_version}
                    key={version.id}
                    onClick={() => closeAfter(() => onActivateVersion(message, version))}
                    type="button"
                  >
                    版本 {version.version_index}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </span>
    </div>
  );
}
