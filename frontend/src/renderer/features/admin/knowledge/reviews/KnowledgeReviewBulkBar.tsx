import type { KnowledgeReviewResponse } from "../../../../shared/api/types";
import {
  batchSkipReason,
  canBatchApprove,
  canBatchReject,
  type KnowledgeReviewBatchResult,
  type KnowledgeReviewDrafts,
} from "./knowledgeReviewView";

export type KnowledgeReviewBulkBarProps = {
  adminLoading: boolean;
  batchBusy: boolean;
  drafts: KnowledgeReviewDrafts;
  lastResult: KnowledgeReviewBatchResult | null;
  selectedItems: KnowledgeReviewResponse[];
  onBatchReview: (action: "approved" | "rejected") => Promise<void>;
  onClearSelection: () => void;
};

export function KnowledgeReviewBulkBar({
  adminLoading,
  batchBusy,
  drafts,
  lastResult,
  onBatchReview,
  onClearSelection,
  selectedItems,
}: KnowledgeReviewBulkBarProps) {
  const approvable = selectedItems.filter((item) => canBatchApprove(item, drafts));
  const rejectable = selectedItems.filter(canBatchReject);
  const disabled = adminLoading || batchBusy || selectedItems.length === 0;

  return (
    <div className="admin-knowledge-review-bulk">
      <div>
        <strong>已选 {selectedItems.length} 条</strong>
        <span>
          可批量通过 {approvable.length} 条 · 可批量驳回 {rejectable.length} 条
        </span>
      </div>
      <div className="admin-knowledge-review-bulk-actions">
        <button className="ghost-button" disabled={disabled || approvable.length === 0} onClick={() => void onBatchReview("approved")} type="button">
          批量通过
        </button>
        <button className="ghost-button" disabled={disabled || rejectable.length === 0} onClick={() => void onBatchReview("rejected")} type="button">
          批量驳回
        </button>
        <button className="ghost-button" disabled={disabled} onClick={onClearSelection} type="button">
          清空选择
        </button>
      </div>
      {selectedItems.length ? (
        <p>
          批量通过会跳过已编辑草稿、非 pending、citation-fixer 状态不明项。批量仅作用于当前可见页已选项。
          {selectedItems.some((item) => batchSkipReason(item, "approved", drafts)) ? " 当前选择中存在批量通过不可处理项。" : ""}
        </p>
      ) : null}
      {lastResult ? (
        <div className="admin-knowledge-review-bulk-result">
          <strong>
            {lastResult.action === "approved" ? "批量通过" : "批量驳回"}结果：成功 {lastResult.success.length} · 失败 {lastResult.failed.length} · 跳过 {lastResult.skipped.length}
          </strong>
          {[...lastResult.failed, ...lastResult.skipped].length ? (
            <ul>
              {lastResult.failed.map((item) => (
                <li key={`failed-${item.id}`}>失败 #{item.id} {item.source}：{item.reason || "未知错误"}</li>
              ))}
              {lastResult.skipped.map((item) => (
                <li key={`skipped-${item.id}`}>跳过 #{item.id} {item.source}：{item.reason || "不符合批量条件"}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
