import type { KnowledgeReviewResponse } from "../../../../shared/api/types";

export type KnowledgeReviewDrafts = Record<number, string>;

export type KnowledgeReviewBatchItemResult = {
  id: number;
  source: string;
  reason?: string;
};

export type KnowledgeReviewBatchResult = {
  action: "approved" | "rejected";
  success: KnowledgeReviewBatchItemResult[];
  failed: KnowledgeReviewBatchItemResult[];
  skipped: KnowledgeReviewBatchItemResult[];
};

export function filterKnowledgeReviews(reviews: KnowledgeReviewResponse[], search: string): KnowledgeReviewResponse[] {
  const query = search.trim().toLowerCase();
  if (!query) return reviews;
  return reviews.filter((item) => (
    String(item.id).includes(query)
    || (item.source ?? "").toLowerCase().includes(query)
    || item.content.toLowerCase().includes(query)
  ));
}

export function isPendingReview(item: KnowledgeReviewResponse) {
  return item.status === "pending";
}

export function canSubmitCitationFixer(item: KnowledgeReviewResponse) {
  return item.source.startsWith("gbrain_answer_correction:") || item.source.startsWith("gbrain_think_review:");
}

export function reviewSourceLabel(item: KnowledgeReviewResponse) {
  if (!item.source) return "候选知识";
  if (item.source.startsWith("gbrain_answer_correction:")) return "GBrain 回答修正";
  if (item.source.startsWith("gbrain_think_review:")) return "GBrain Think 审核";
  if (item.source.startsWith("project:")) return "项目知识";
  return item.source;
}

export function getDraftContent(item: KnowledgeReviewResponse, drafts: KnowledgeReviewDrafts) {
  return drafts[item.id] ?? item.content;
}

export function isDraftEdited(item: KnowledgeReviewResponse, drafts: KnowledgeReviewDrafts) {
  return getDraftContent(item, drafts) !== item.content;
}

export function canBatchApprove(item: KnowledgeReviewResponse, drafts: KnowledgeReviewDrafts) {
  if (!isPendingReview(item)) return false;
  if (isDraftEdited(item, drafts)) return false;
  if (canSubmitCitationFixer(item)) return false;
  return true;
}

export function canBatchReject(item: KnowledgeReviewResponse) {
  return isPendingReview(item);
}

export function batchSkipReason(
  item: KnowledgeReviewResponse,
  action: "approved" | "rejected",
  drafts: KnowledgeReviewDrafts,
) {
  if (!isPendingReview(item)) return "不是 pending 状态";
  if (action === "approved" && isDraftEdited(item, drafts)) return "已有本地编辑草稿，只能单条审核";
  if (action === "approved" && canSubmitCitationFixer(item)) return "citation-fixer 状态不明，只能单条审核";
  return "";
}

export function buildReviewDiffSummary(original: string, proposed: string) {
  if (original === proposed) {
    return { changed: false, text: "未修改，批量通过时可使用原内容。", tone: "neutral" as const };
  }
  if (!proposed.trim()) {
    return { changed: true, text: "编辑草稿为空，不能通过。", tone: "danger" as const };
  }
  const originalLines = lineCount(original);
  const proposedLines = lineCount(proposed);
  const delta = proposed.length - original.length;
  const deltaText = delta === 0 ? "字符数未变" : `${delta > 0 ? "+" : ""}${delta} 字符`;
  return {
    changed: true,
    text: `已修改本地草稿：${originalLines} 行 -> ${proposedLines} 行，${deltaText}。`,
    tone: "changed" as const,
  };
}

export function itemResult(item: KnowledgeReviewResponse, reason?: string): KnowledgeReviewBatchItemResult {
  return {
    id: item.id,
    source: item.source || "候选知识",
    reason,
  };
}

function lineCount(value: string) {
  if (!value) return 0;
  return value.split(/\r?\n/).length;
}
