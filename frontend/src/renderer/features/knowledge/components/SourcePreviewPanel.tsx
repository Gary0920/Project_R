import { renderMessageContent } from "../../chat/messageContent";
import type { KnowledgeSourcePreview } from "../sourcePreview";
import { evidenceContextFromTrace, normalizeSourceEvidence } from "../sourceEvidence";
import { SourceEvidencePanel } from "./SourceEvidencePanel";

export type SourcePreviewPanelProps = {
  preview: KnowledgeSourcePreview | null;
};

export function SourcePreviewPanel({ preview }: SourcePreviewPanelProps) {
  if (!preview) {
    return <div className="prompt-empty">点击 AI 回复中的来源标签后，会在这里预览本轮引用片段。</div>;
  }
  const source = normalizeSourceEvidence(preview.source, preview.index, evidenceContextFromTrace(preview.contextTrace));
  return (
    <div className="source-preview-body">
      <div className="source-preview-heading">
        <span className="source-preview-index">[{preview.index}]</span>
        <span className="source-preview-scope">{source.scopeLabel}</span>
      </div>
      <h3>{source.displayTitle}</h3>
      {source.evidenceExcerpt ? (
        <div className="source-preview-excerpt">
          <strong>证据片段</strong>
          <div className="source-preview-markdown">
            {renderMessageContent(source.evidenceExcerpt)}
          </div>
        </div>
      ) : (
        <div className="source-preview-degraded">
          当前 GBrain 仅返回引用坐标，未返回可展示的原文片段。
        </div>
      )}
      <dl className="source-preview-meta">
        <div>
          <dt>来源范围</dt>
          <dd>{source.scopeLabel}</dd>
        </div>
        {source.originalSourceFile ? (
          <div>
            <dt>原始文件</dt>
            <dd>{source.originalSourceFile}</dd>
          </div>
        ) : null}
        <div>
          <dt>定位</dt>
          <dd>{source.locatorLabel}</dd>
        </div>
      </dl>
      <SourceEvidencePanel evidence={source} compact />
      <div className="source-preview-boundary">
        仅显示本轮回答实际引用片段；不提供完整知识库文件、source 列表或入库状态浏览。
      </div>
      <details className="source-preview-technical">
        <summary>技术详情</summary>
        <dl>
          <div>
            <dt>source slug</dt>
            <dd>{source.sourceSlug || "无"}</dd>
          </div>
          <div>
            <dt>page slug</dt>
            <dd>{source.pageSlug || "无"}</dd>
          </div>
          <div>
            <dt>row</dt>
            <dd>{source.rowNum ?? "page"}</dd>
          </div>
        </dl>
      </details>
    </div>
  );
}
