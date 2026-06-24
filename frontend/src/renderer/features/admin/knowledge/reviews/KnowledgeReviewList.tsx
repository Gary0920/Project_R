import type { KnowledgeReviewResponse } from "../../../../shared/api/types";
import { canBatchApprove, canBatchReject, isDraftEdited, reviewListPreview, reviewSourceLabel, type KnowledgeReviewDrafts } from "./knowledgeReviewView";

export type KnowledgeReviewListProps = {
  adminLoading: boolean;
  drafts: KnowledgeReviewDrafts;
  formatDate: (value: string | number) => string;
  items: KnowledgeReviewResponse[];
  selectedId: number | null;
  selectedIds: Set<number>;
  onSelect: (item: KnowledgeReviewResponse) => void;
  onToggleSelected: (item: KnowledgeReviewResponse, checked: boolean) => void;
};

export function KnowledgeReviewList({
  adminLoading,
  drafts,
  formatDate,
  items,
  onSelect,
  onToggleSelected,
  selectedId,
  selectedIds,
}: KnowledgeReviewListProps) {
  if (!items.length) {
    return <p className="admin-knowledge-review-empty">当前页没有待审核知识。</p>;
  }

  return (
    <div className="admin-knowledge-review-list">
      {items.map((item) => {
        const checked = selectedIds.has(item.id);
        const selectable = canBatchApprove(item, drafts) || canBatchReject(item);
        return (
          <article
            className={`admin-knowledge-review-list-item ${selectedId === item.id ? "is-active" : ""}`}
            key={item.id}
            onClick={() => onSelect(item)}
          >
            <label className="admin-knowledge-review-check" onClick={(event) => event.stopPropagation()}>
              <input
                checked={checked}
                disabled={adminLoading || !selectable}
                onChange={(event) => onToggleSelected(item, event.target.checked)}
                type="checkbox"
              />
            </label>
            <div className="admin-knowledge-review-list-main">
              <div className="admin-knowledge-review-list-title">
                <strong>#{item.id} {reviewSourceLabel(item)}</strong>
                <span className={`admin-knowledge-review-status is-${item.status}`}>{item.status}</span>
              </div>
              <p>{reviewListPreview(item)}</p>
              <span>{formatDate(item.created_at)}{isDraftEdited(item, drafts) ? " · 已编辑草稿" : ""}</span>
            </div>
          </article>
        );
      })}
    </div>
  );
}
