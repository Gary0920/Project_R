import { CopyIcon, XmarkIcon } from "../../../shared/icons/LineIcons";
import { TEXT_TRANSFORM_LABELS, type TextTransformResult } from "../textTransform";

export type TextTransformResultCardProps = {
  result: TextTransformResult;
  onApply: (text: string) => void;
  onClear: () => void;
  onCopy: (text: string) => Promise<void>;
};

export function TextTransformResultCard({
  result,
  onApply,
  onClear,
  onCopy,
}: TextTransformResultCardProps) {
  return (
    <div className="text-transform-result-card">
      <div className="text-transform-result-header">
        <strong>{TEXT_TRANSFORM_LABELS[result.action]}结果</strong>
        <span>{result.model}</span>
        <button onClick={onClear} title="关闭结果" type="button"><XmarkIcon /></button>
      </div>
      <pre>{result.text}</pre>
      <div className="text-transform-result-actions">
        <button className="btn-secondary" onClick={() => void onCopy(result.text)} type="button">
          <CopyIcon />
          复制
        </button>
        <button className="btn-primary" onClick={() => onApply(result.text)} type="button">替换输入框</button>
      </div>
    </div>
  );
}
