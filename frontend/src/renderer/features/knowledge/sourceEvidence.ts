import type { ChatContextTraceResponse, ChatSourceResponse } from "../../shared/api/types";
import type {
  SourceEvidence,
  SourceEvidenceContext,
  SourceEvidenceFilter,
  SourceEvidenceIssue,
  SourceEvidenceKind,
  SourceEvidenceStatusLevel,
} from "./sourceEvidenceTypes";

const FILTER_LABELS: Record<SourceEvidenceFilter, string> = {
  all: "全部",
  company: "公司知识",
  project: "项目资料",
  customer: "客户情报",
  external: "外部来源",
  unknown: "授权来源",
  issues: "需核对",
};

export function sourceEvidenceFilterLabel(filter: SourceEvidenceFilter) {
  return FILTER_LABELS[filter];
}

export function sourceEvidenceKindLabel(kind: Exclude<SourceEvidenceKind, "all">) {
  return FILTER_LABELS[kind];
}

export function evidenceContextFromTrace(contextTrace?: ChatContextTraceResponse | null): SourceEvidenceContext {
  const gbrainThink = contextTrace?.gbrain_think;
  return {
    conflicts: gbrainThink?.conflicts?.filter(Boolean) ?? [],
    gaps: gbrainThink?.gaps?.filter(Boolean) ?? [],
    warnings: gbrainThink?.warnings?.filter(Boolean) ?? [],
  };
}

export function buildSourceEvidences(
  sources?: ChatSourceResponse[] | null,
  contextTrace?: ChatContextTraceResponse | null,
): SourceEvidence[] {
  const context = evidenceContextFromTrace(contextTrace);
  return (sources ?? []).map((source, index) => normalizeSourceEvidence(source, index + 1, context));
}

export function normalizeSourceEvidence(
  source: ChatSourceResponse,
  index: number,
  context: SourceEvidenceContext = {},
): SourceEvidence {
  const kind = inferSourceEvidenceKind(source);
  const metadataOnly = isMetadataOnlySource(source);
  const evidenceExcerpt = metadataOnly ? "" : (source.evidence_excerpt || source.content || "").trim();
  const locatorLabel = source.locator_label || sourceLocatorLabel(source);
  const limitations = sourceLimitations(source, metadataOnly, evidenceExcerpt);
  const issues = sourceIssues(context);
  const statusLevel = sourceStatusLevel(issues, limitations);
  const displayTitle = source.display_title || source.source_title || "引用来源";
  return {
    displayTitle,
    evidenceExcerpt,
    excerpt: evidenceExcerpt,
    fileName: source.original_source_file || source.source_file || source.file || "",
    id: `${source.file || source.source_file || "source"}-${index}`,
    index,
    isCitedInThisAnswer: true,
    issues,
    kind,
    limitations,
    locatorLabel,
    metadataOnly,
    originalSourceFile: source.original_source_file || source.source_file || "",
    page: source.source_page,
    pageSlug: source.page_slug,
    line: source.source_line,
    rawSource: source,
    rowNum: source.row_num,
    scopeLabel: sourceEvidenceKindLabel(kind),
    sourceSlug: source.source_slug,
    statusLevel,
    statusText: sourceStatusText(statusLevel),
    title: displayTitle,
  };
}

export function visibleEvidenceFilters(evidences: SourceEvidence[]): SourceEvidenceFilter[] {
  const filters: SourceEvidenceFilter[] = ["all"];
  (["company", "project", "customer", "external"] as SourceEvidenceFilter[]).forEach((filter) => {
    if (evidences.some((item) => item.kind === filter)) filters.push(filter);
  });
  if (evidences.some((item) => item.issues.length || item.statusLevel !== "normal")) filters.push("issues");
  return filters;
}

export function filterSourceEvidences(evidences: SourceEvidence[], filter: SourceEvidenceFilter) {
  if (filter === "all") return evidences;
  if (filter === "issues") return evidences.filter((item) => item.issues.length || item.statusLevel !== "normal");
  return evidences.filter((item) => item.kind === filter);
}

export function inferSourceEvidenceKind(source: ChatSourceResponse): Exclude<SourceEvidenceKind, "all"> {
  const file = `${source.source_id || ""} ${source.file || ""} ${source.source_file || ""} ${source.source_locator || ""}`.toLowerCase();
  if (source.source_file?.startsWith("http") || file.includes("web:") || file.includes("http://") || file.includes("https://")) return "external";
  if (file.includes("customer") || file.includes("crm")) return "customer";
  if (file.includes("company-wiki") || file.includes("company")) return "company";
  if (file.includes("project")) return "project";
  return "unknown";
}

export function sourceLocatorLabel(source: ChatSourceResponse) {
  const parts = [
    source.section_path,
    source.source_page != null ? `第 ${source.source_page} 页` : null,
    source.source_line != null ? `第 ${source.source_line} 行` : null,
    source.source_locator,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "文件级定位";
}

function sourceLimitations(source: ChatSourceResponse, metadataOnly: boolean, evidenceExcerpt: string) {
  const limitations: string[] = ["筛选仅作用于本轮引用来源，不会浏览完整知识库。"];
  if (metadataOnly || !evidenceExcerpt) {
    limitations.push("当前 GBrain 仅返回引用坐标，未返回可展示的原文片段。");
  }
  if (source.source_page == null && source.source_line == null && !source.source_locator) {
    limitations.push("该来源定位精度有限，仅能定位到文件或片段级。");
  }
  if (!metadataOnly && !evidenceExcerpt) {
    limitations.push("该来源没有返回可展示片段，请回到原文件核对。");
  }
  return limitations;
}

export function isMetadataOnlySource(source: ChatSourceResponse) {
  if (source.metadata_only === true) return true;
  const text = (source.content || "").trim();
  if (!text) return false;
  return /^GBrain think citation\b/i.test(text)
    && /(^|\n)\s*-\s*source\s*:/i.test(text)
    && /(^|\n)\s*-\s*page\s*:/i.test(text)
    && /(^|\n)\s*-\s*row\s*:/i.test(text);
}

function sourceIssues(context: SourceEvidenceContext): SourceEvidenceIssue[] {
  return [
    ...(context.conflicts ?? []).map((text) => ({ kind: "conflict" as const, text })),
    ...(context.gaps ?? []).map((text) => ({ kind: "gap" as const, text })),
    ...(context.warnings ?? []).map((text) => ({ kind: "warning" as const, text })),
  ];
}

function sourceStatusLevel(issues: SourceEvidenceIssue[], limitations: string[]): SourceEvidenceStatusLevel {
  if (issues.some((item) => item.kind === "conflict")) return "conflict";
  if (issues.some((item) => item.kind === "gap")) return "gap";
  if (issues.some((item) => item.kind === "warning")) return "warning";
  if (limitations.some((item) => item.includes("定位精度有限") || item.includes("没有返回"))) return "limited";
  return "normal";
}

function sourceStatusText(level: SourceEvidenceStatusLevel) {
  if (level === "conflict") return "不同来源存在冲突，需要核对。";
  if (level === "gap") return "回答存在资料缺口。";
  if (level === "warning") return "系统对该引用有风险提示。";
  if (level === "limited") return "该来源定位有限。";
  return "该来源已被本次回答引用。";
}
