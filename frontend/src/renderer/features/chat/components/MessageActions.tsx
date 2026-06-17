import { AgentIcon, CopyIcon, EditIcon, RefreshIcon, TrashIcon } from "../../../shared/icons/LineIcons";
import type { ChatMessage } from "../state";
import type { TextTransformAction } from "../textTransform";
import { TextTransformButtons } from "./TextTransformButtons";

export type MessageActionsProps = {
  copied: boolean;
  isBusy: boolean;
  message: ChatMessage;
  onCopy: (message: ChatMessage) => void;
  onDelete: (message: ChatMessage) => void;
  onFeedback: (message: ChatMessage) => void;
  onQuote: (message: ChatMessage) => void;
  onRegenerate: (message: ChatMessage) => void;
  onStartEdit: (message: ChatMessage) => void;
  onSwitchToAgent: (messageId: number) => void;
  onTransform?: (message: ChatMessage, action: TextTransformAction) => void;
};

export function MessageActions({
  copied,
  isBusy,
  message,
  onCopy,
  onDelete,
  onFeedback,
  onQuote,
  onRegenerate,
  onStartEdit,
  onSwitchToAgent,
  onTransform,
}: MessageActionsProps) {
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
        <button
          className="message-action-btn"
          disabled={message.isOptimistic || isBusy}
          onClick={() => onRegenerate(message)}
          title="重新生成"
          type="button"
        >
          <RefreshIcon />
        </button>
      ) : null}
      {onTransform ? (
        <TextTransformButtons disabled={message.isOptimistic || isBusy} message={message} onTransform={onTransform} />
      ) : null}
      {message.role === "user" ? (
        <button
          className="message-action-btn"
          disabled={message.isOptimistic || isBusy}
          onClick={() => onStartEdit(message)}
          title="编辑并开启新分支"
          type="button"
        >
          <EditIcon />
        </button>
      ) : null}
      {message.role === "assistant" ? (
        <button className="message-action-btn" onClick={() => onSwitchToAgent(message.id)} title="切换到 Agent" type="button">
          <AgentIcon />
        </button>
      ) : null}
      <button
        className="message-action-btn"
        disabled={message.isOptimistic}
        onClick={() => onQuote(message)}
        title="引用"
        type="button"
      >
        <span style={{ fontSize: 11 }}>❝</span>
      </button>
      {message.role === "assistant" ? (
        <button
          className={`message-action-btn ${message.feedback_rating ? "is-rated" : ""}`}
          disabled={message.isOptimistic || isBusy}
          onClick={() => onFeedback(message)}
          title="评分与意见"
          type="button"
        >
          <span className="message-action-star">★</span>
        </button>
      ) : null}
      <button
        className="message-action-btn"
        disabled={message.isOptimistic || isBusy}
        onClick={() => onDelete(message)}
        title="删除当前问答"
        type="button"
      >
        <TrashIcon />
      </button>
    </div>
  );
}
