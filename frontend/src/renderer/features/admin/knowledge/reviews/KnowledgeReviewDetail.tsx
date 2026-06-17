import type { KnowledgeReviewResponse } from "../../../../shared/api/types";
import {
  buildReviewDiffSummary,
  canSubmitCitationFixer,
  getDraftContent,
  isPendingReview,
  reviewSourceLabel,
  type KnowledgeReviewDrafts,
} from "./knowledgeReviewView";

export type KnowledgeReviewDetailProps = {
  adminLoading: boolean;
  drafts: KnowledgeReviewDrafts;
  formatDate: (value: string | number) => string;
  item: KnowledgeReviewResponse | null;
  onDraftChange: (item: KnowledgeReviewResponse, value: string) => void;
  onReview: (item: KnowledgeReviewResponse, status: "approved" | "rejected", content?: string) => Promise<boolean>;
  onSubmitCitationFixer: (item: KnowledgeReviewResponse) => Promise<void>;
};

export function KnowledgeReviewDetail({
  adminLoading,
  drafts,
  formatDate,
  item,
  onDraftChange,
  onReview,
  onSubmitCitationFixer,
}: KnowledgeReviewDetailProps) {
  if (!item) {
    return (
      <aside className="admin-knowledge-review-detail">
        <p className="admin-knowledge-review-empty">请选择一条审核项查看详情。</p>
      </aside>
    );
  }

  const draft = getDraftContent(item, drafts);
  const diff = buildReviewDiffSummary(item.content, draft);
  const canApprove = isPendingReview(item) && Boolean(draft.trim());
  const canReject = isPendingReview(item);

  return (
    <aside className="admin-knowledge-review-detail">
      <header className="admin-knowledge-review-detail-header">
        <div>
          <strong>#{item.id} {reviewSourceLabel(item)}</strong>
          <span>{item.source || "候选知识"} · {formatDate(item.created_at)}</span>
        </div>
        <span className={`admin-knowledge-review-status is-${item.status}`}>{item.status}</span>
      </header>

      <div className={`admin-knowledge-review-diff-note is-${diff.tone}`}>
        {diff.text}
      </div>

      <div className="admin-knowledge-review-diff">
        <section>
          <strong>原审核内容</strong>
          <pre>{item.content || "空内容"}</pre>
        </section>
        <section>
          <strong>本次编辑草稿</strong>
          <textarea
            disabled={adminLoading || !isPendingReview(item)}
            onChange={(event) => onDraftChange(item, event.target.value)}
            value={draft}
          />
        </section>
      </div>

      <div className="admin-knowledge-review-detail-actions">
        {canSubmitCitationFixer(item) ? (
          <button className="ghost-button" disabled={adminLoading} onClick={() => void onSubmitCitationFixer(item)} type="button">
            引用修复
          </button>
        ) : null}
        <button
          className="ghost-button"
          disabled={adminLoading || !canApprove}
          onClick={() => void onReview(item, "approved", draft)}
          type="button"
        >
          通过
        </button>
        <button
          className="ghost-button"
          disabled={adminLoading || !canReject}
          onClick={() => void onReview(item, "rejected")}
          type="button"
        >
          驳回
        </button>
      </div>
    </aside>
  );
}
