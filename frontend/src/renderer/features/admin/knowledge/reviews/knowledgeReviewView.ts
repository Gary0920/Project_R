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

export type GBrainThinkReviewSummary = {
  adminSummary: string;
  answerExcerpt: string;
  citations: string[];
  conflicts: string[];
  gaps: string[];
  guidance: string;
  isGBrainThink: true;
  listPreview: string;
  question: string;
  topic: string;
  userBusinessContext: string;
  userExpectedKnowledge: string;
  userNote: string;
  userSourceHint: string;
  warnings: string[];
};

const GBRAIN_THINK_REVIEW_PREFIX = "gbrain_think_review:";
const EMPTY_SECTION_VALUES = new Set(["", "无", "none", "无 / none", "- 无", "- none", "- 无 / none"]);

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

export function isGBrainThinkReview(item: KnowledgeReviewResponse) {
  return item.source.startsWith(GBRAIN_THINK_REVIEW_PREFIX);
}

export function reviewSourceLabel(item: KnowledgeReviewResponse) {
  if (!item.source) return "候选知识";
  if (item.source.startsWith("gbrain_answer_correction:")) return "GBrain 回答修正";
  if (isGBrainThinkReview(item)) return "知识缺口反馈";
  if (item.source.startsWith("project:")) return "项目知识";
  return item.source;
}

export function getDraftContent(item: KnowledgeReviewResponse, drafts: KnowledgeReviewDrafts) {
  if (isGBrainThinkReview(item)) return drafts[item.id] ?? "";
  return drafts[item.id] ?? item.content;
}

export function isDraftEdited(item: KnowledgeReviewResponse, drafts: KnowledgeReviewDrafts) {
  if (isGBrainThinkReview(item)) return drafts[item.id] !== undefined && drafts[item.id] !== "";
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

export function summarizeKnowledgeReview(item: KnowledgeReviewResponse): GBrainThinkReviewSummary | null {
  if (!isGBrainThinkReview(item)) return null;
  const userSupplement = parseUserSupplement(extractMarkdownSection(item.content, "用户补充信息 / User Supplement"));
  const question = extractMarkdownSection(item.content, "原问题 / Original Question");
  const answerExcerpt = extractMarkdownSection(item.content, "原回答摘录 / Answer Excerpt");
  const gaps = parseIssueList(extractMarkdownSection(item.content, "GBrain 缺口 / Gaps"));
  const conflicts = parseIssueList(extractMarkdownSection(item.content, "GBrain 冲突 / Conflicts"));
  const warnings = filterSecondaryIssues([...gaps, ...conflicts], parseIssueList(extractMarkdownSection(item.content, "GBrain 警告 / Warnings")));
  const citations = parseCitationList(extractMarkdownSection(item.content, "GBrain 引用来源 / GBrain Citations"));
  const guidance = extractMarkdownSection(item.content, "管理员处理建议 / Admin Triage Guidance");
  const topic = firstLine(userSupplement.expectedKnowledge) || firstLine(gaps[0] ?? "") || firstLine(question) || "待补充知识";
  const adminSummary = buildGBrainAdminSummary({
    businessContext: userSupplement.businessContext,
    conflicts,
    expectedKnowledge: userSupplement.expectedKnowledge,
    gaps,
    question,
    sourceHint: userSupplement.sourceHint,
    topic,
    userNote: userSupplement.userNote,
    warnings,
  });
  const listPreview = topic || "等待管理员判断是否需要补充资料、引用修复或沉淀为知识。";
  return {
    adminSummary,
    answerExcerpt,
    citations,
    conflicts,
    gaps,
    guidance,
    isGBrainThink: true,
    listPreview,
    question,
    topic,
    userBusinessContext: userSupplement.businessContext,
    userExpectedKnowledge: userSupplement.expectedKnowledge,
    userNote: userSupplement.userNote,
    userSourceHint: userSupplement.sourceHint,
    warnings,
  };
}

export function reviewListPreview(item: KnowledgeReviewResponse) {
  const summary = summarizeKnowledgeReview(item);
  if (summary) return summary.listPreview;
  return item.content.slice(0, 180) || "空内容";
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

function extractMarkdownSection(content: string, heading: string) {
  const pattern = new RegExp(`^##\\s+${escapeRegExp(heading)}\\s*\\n+([\\s\\S]*?)(?=\\n##\\s+|$)`, "m");
  const match = content.match(pattern);
  return (match?.[1] ?? "").trim();
}

function parseIssueList(section: string) {
  return section
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^[-*]\s*/, ""))
    .filter((line) => !EMPTY_SECTION_VALUES.has(line.toLowerCase()));
}

function parseCitationList(section: string) {
  return section
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^\d+\.\s+`/.test(line))
    .map((line) => line.replace(/^\d+\.\s+`([^`]+)`.*$/, "$1"))
    .slice(0, 4);
}

function parseUserSupplement(section: string) {
  return {
    businessContext: extractBulletValue(section, "业务场景 / Business Context"),
    expectedKnowledge: extractBulletValue(section, "期望补充知识 / Expected Knowledge"),
    sourceHint: extractBulletValue(section, "可参考来源 / Source Hint"),
    userNote: extractBulletValue(section, "自由说明 / User Note"),
  };
}

function buildGBrainAdminSummary({
  businessContext,
  conflicts,
  expectedKnowledge,
  gaps,
  question,
  sourceHint,
  topic,
  userNote,
  warnings,
}: {
  businessContext: string;
  conflicts: string[];
  expectedKnowledge: string;
  gaps: string[];
  question: string;
  sourceHint: string;
  topic: string;
  userNote: string;
  warnings: string[];
}) {
  const userIntent = firstLine(expectedKnowledge) || firstLine(userNote) || firstLine(businessContext) || firstLine(question) || "用户希望管理员判断是否需要补充公司知识。";
  const signal = firstLine(gaps[0] ?? "") || firstLine(conflicts[0] ?? "") || firstLine(warnings[0] ?? "") || topic;
  const sourceText = sourceHint ? `参考线索：${sourceHint}` : "用户未提供明确参考来源。";
  return `用户需要确认“${userIntent}”；GBrain 判断的主要问题是“${signal}”。${sourceText}`;
}

function extractBulletValue(section: string, label: string) {
  const prefix = `- ${label}:`;
  const line = section.split(/\r?\n/).find((item) => item.trim().startsWith(prefix));
  return line ? line.trim().slice(prefix.length).trim() : "";
}

function filterSecondaryIssues(primary: string[], secondary: string[]) {
  const primaryKeys = new Set(primary.map(issueKey).filter(Boolean));
  return secondary.filter((item) => {
    const key = issueKey(item);
    return key && !primaryKeys.has(key);
  });
}

function firstLine(value: string) {
  return value.split(/\r?\n/).map((line) => line.trim()).find(Boolean) ?? "";
}

function issueKey(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s。．.，,、；;：:！!？?（）()[\]【】"'`_-]/g, "");
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
