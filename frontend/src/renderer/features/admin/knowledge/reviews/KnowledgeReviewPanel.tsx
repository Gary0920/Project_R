import { useEffect, useMemo, useState } from "react";

import type { KnowledgeReviewResponse } from "../../../../shared/api/types";
import { KnowledgeReviewBulkBar } from "./KnowledgeReviewBulkBar";
import { KnowledgeReviewDetail } from "./KnowledgeReviewDetail";
import { KnowledgeReviewList } from "./KnowledgeReviewList";
import {
  batchSkipReason,
  canBatchApprove,
  canBatchReject,
  filterKnowledgeReviews,
  getDraftContent,
  itemResult,
  type KnowledgeReviewBatchResult,
  type KnowledgeReviewDrafts,
} from "./knowledgeReviewView";

const REVIEW_PAGE_SIZE = 10;

export type KnowledgeReviewPanelProps = {
  adminLoading: boolean;
  formatDate: (value: string | number) => string;
  knowledgeReviews: KnowledgeReviewResponse[];
  reviewPage: number;
  reviewSearch: string;
  setReviewPage: (value: number | ((prev: number) => number)) => void;
  setReviewSearch: (value: string | ((prev: string) => string)) => void;
  onReviewKnowledge: (item: KnowledgeReviewResponse, status: "approved" | "rejected", content?: string) => Promise<boolean>;
  onSubmitReviewCitationFixer: (item: KnowledgeReviewResponse) => Promise<void>;
};

export function KnowledgeReviewPanel({
  adminLoading,
  formatDate,
  knowledgeReviews,
  onReviewKnowledge,
  onSubmitReviewCitationFixer,
  reviewPage,
  reviewSearch,
  setReviewPage,
  setReviewSearch,
}: KnowledgeReviewPanelProps) {
  const [drafts, setDrafts] = useState<KnowledgeReviewDrafts>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  const [lastBatchResult, setLastBatchResult] = useState<KnowledgeReviewBatchResult | null>(null);

  const filtered = useMemo(() => filterKnowledgeReviews(knowledgeReviews, reviewSearch), [knowledgeReviews, reviewSearch]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / REVIEW_PAGE_SIZE));
  const safePage = Math.min(Math.max(1, reviewPage), totalPages);
  const visibleItems = filtered.slice((safePage - 1) * REVIEW_PAGE_SIZE, safePage * REVIEW_PAGE_SIZE);
  const selectedItem = visibleItems.find((item) => item.id === selectedId) ?? visibleItems[0] ?? null;
  const selectedItems = visibleItems.filter((item) => selectedIds.has(item.id));

  useEffect(() => {
    setSelectedIds(new Set());
    setLastBatchResult(null);
  }, [reviewSearch, safePage]);

  useEffect(() => {
    if (reviewPage !== safePage) setReviewPage(safePage);
  }, [reviewPage, safePage, setReviewPage]);

  useEffect(() => {
    if (!selectedItem) {
      setSelectedId(null);
      return;
    }
    if (selectedId !== selectedItem.id) setSelectedId(selectedItem.id);
  }, [selectedId, selectedItem]);

  function updateSearch(value: string) {
    setReviewSearch(value);
    setReviewPage(1);
  }

  function toggleSelected(item: KnowledgeReviewResponse, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(item.id);
      else next.delete(item.id);
      return next;
    });
  }

  function updateDraft(item: KnowledgeReviewResponse, value: string) {
    setDrafts((current) => ({ ...current, [item.id]: value }));
  }

  async function reviewOne(item: KnowledgeReviewResponse, status: "approved" | "rejected", content?: string) {
    const ok = await onReviewKnowledge(item, status, status === "approved" ? content : undefined);
    if (ok) {
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
    }
    return ok;
  }

  async function runBatch(action: "approved" | "rejected") {
    const targets = selectedItems;
    if (!targets.length) return;
    const skipped = targets
      .map((item) => ({ item, reason: batchSkipReason(item, action, drafts) }))
      .filter(({ reason }) => Boolean(reason));
    const eligible = targets.filter((item) => action === "approved" ? canBatchApprove(item, drafts) : canBatchReject(item));
    const confirmText = action === "approved"
      ? `确认批量通过当前页 ${eligible.length} 条审核项？将跳过 ${skipped.length} 条不符合条件的项。`
      : `确认批量驳回当前页 ${eligible.length} 条审核项？将跳过 ${skipped.length} 条不符合条件的项。`;
    if (!window.confirm(confirmText)) return;

    const result: KnowledgeReviewBatchResult = {
      action,
      success: [],
      failed: [],
      skipped: skipped.map(({ item, reason }) => itemResult(item, reason)),
    };
    setBatchBusy(true);
    setLastBatchResult(null);
    try {
      for (const item of eligible) {
        const ok = await onReviewKnowledge(item, action, action === "approved" ? getDraftContent(item, drafts) : undefined);
        if (ok) result.success.push(itemResult(item));
        else result.failed.push(itemResult(item, "接口返回失败或请求异常"));
      }
      setSelectedIds(new Set());
      setLastBatchResult(result);
    } finally {
      setBatchBusy(false);
    }
  }

  return (
    <div className="settings-section admin-knowledge-review">
      <div className="settings-section-header">
        <h3>知识审核</h3>
        <p>G6.0 审核工作台 MVP：本地草稿对比、单条审核和当前页安全批量操作。</p>
      </div>

      <div className="admin-knowledge-review-toolbar">
        <input
          className="admin-search"
          placeholder="搜索 id、来源或内容"
          value={reviewSearch}
          onChange={(event) => updateSearch(event.target.value)}
        />
        <span>{filtered.length} 条匹配</span>
      </div>

      <KnowledgeReviewBulkBar
        adminLoading={adminLoading}
        batchBusy={batchBusy}
        drafts={drafts}
        lastResult={lastBatchResult}
        selectedItems={selectedItems}
        onBatchReview={runBatch}
        onClearSelection={() => setSelectedIds(new Set())}
      />

      <div className="admin-knowledge-review-workbench">
        <section className="admin-knowledge-review-master">
          <KnowledgeReviewList
            adminLoading={adminLoading || batchBusy}
            drafts={drafts}
            formatDate={formatDate}
            items={visibleItems}
            selectedId={selectedItem?.id ?? null}
            selectedIds={selectedIds}
            onSelect={(item) => setSelectedId(item.id)}
            onToggleSelected={toggleSelected}
          />
          {totalPages > 1 ? (
            <div className="admin-pagination">
              <button disabled={safePage <= 1 || batchBusy} onClick={() => setReviewPage((page) => Math.max(1, page - 1))} type="button">上一页</button>
              <span className="page-info">第 {safePage} / {totalPages} 页</span>
              <button disabled={safePage >= totalPages || batchBusy} onClick={() => setReviewPage((page) => Math.min(totalPages, page + 1))} type="button">下一页</button>
            </div>
          ) : null}
        </section>

        <KnowledgeReviewDetail
          adminLoading={adminLoading || batchBusy}
          drafts={drafts}
          formatDate={formatDate}
          item={selectedItem}
          onDraftChange={updateDraft}
          onReview={reviewOne}
          onSubmitCitationFixer={onSubmitReviewCitationFixer}
        />
      </div>
    </div>
  );
}
