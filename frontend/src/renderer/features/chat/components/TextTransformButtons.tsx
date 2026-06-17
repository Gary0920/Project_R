import type { ChatMessage } from "../state";
import { TEXT_TRANSFORM_LABELS, type TextTransformAction } from "../textTransform";

const ACTIONS: Array<{ action: TextTransformAction; shortLabel: string }> = [
  { action: "rewrite", shortLabel: "改" },
  { action: "translate", shortLabel: "译" },
  { action: "summarize", shortLabel: "摘" },
  { action: "expand", shortLabel: "扩" },
];

export function TextTransformButtons({
  disabled,
  message,
  onTransform,
}: {
  disabled?: boolean;
  message: ChatMessage;
  onTransform: (message: ChatMessage, action: TextTransformAction) => void;
}) {
  return (
    <>
      {ACTIONS.map((item) => (
        <button
          className="message-action-btn is-text-action"
          disabled={disabled}
          key={item.action}
          onClick={() => onTransform(message, item.action)}
          title={`${TEXT_TRANSFORM_LABELS[item.action]}到输入框`}
          type="button"
        >
          {item.shortLabel}
        </button>
      ))}
    </>
  );
}
