import type {
  KnowledgeQualityReportsResponse,
  KnowledgeQualityReportTrendItem,
  KnowledgeRegressionCaseResponse,
  KnowledgeRegressionResponse,
  KnowledgeRegressionSuiteResponse,
} from "../../../shared/api/types";

export type QualityFailureCaseView = {
  id: string;
  suite: "query" | "think";
  reason: string;
};

export type QualityTrendPointView = {
  id: string;
  label: string;
  queryPassRate: number;
  thinkPassRate: number;
  queryFailed: number;
  thinkFailed: number;
};

export type QualityReportView = {
  latest: KnowledgeRegressionResponse | null;
  latestId: string | null;
  reportCount: number;
  statusText: string;
  queryText: string;
  thinkText: string;
  failedCases: QualityFailureCaseView[];
  preflightFailures: string[];
  warnings: string[];
  trendPoints: QualityTrendPointView[];
  trendMessage: string;
};

type FormatDate = (value: string | number) => string;

const INSUFFICIENT_TREND_TEXT = "历史报告数据不足，暂无法形成趋势";

export function buildQualityReportView(
  qualityReports: KnowledgeQualityReportsResponse | null | undefined,
  formatDate: FormatDate,
): QualityReportView {
  const reports = qualityReports?.reports ?? [];
  const latest = qualityReports?.latest ?? reports[0] ?? null;
  const failedCases = latest ? getFailedCases(latest) : [];
  const preflightFailures = latest ? getPreflightFailures(latest) : [];
  const warnings = latest ? getWarnings(latest) : [];
  const trendPoints = getTrendPoints(qualityReports, reports, formatDate);

  return {
    latest,
    latestId: latest?.id ?? null,
    reportCount: qualityReports?.count ?? reports.length,
    statusText: latest ? `${latest.ok ? "通过" : "有失败"}${latest.ran_at ? ` · ${formatDate(latest.ran_at)}` : ""}` : "尚未生成质量报告",
    queryText: suiteSummaryText(latest?.summary?.query, latest?.query),
    thinkText: suiteSummaryText(latest?.summary?.think, latest?.think),
    failedCases,
    preflightFailures,
    warnings,
    trendPoints,
    trendMessage: trendPoints.length >= 2 ? "" : INSUFFICIENT_TREND_TEXT,
  };
}

function suiteSummaryText(
  summary: { total?: number; passed?: number; failed?: number; skipped?: boolean } | undefined,
  suite: KnowledgeRegressionSuiteResponse | undefined,
) {
  if (summary?.skipped || suite?.skipped) return "跳过";
  const total = numberOrNull(summary?.total) ?? numberOrNull(suite?.total);
  const passed = numberOrNull(summary?.passed) ?? numberOrNull(suite?.passed);
  const failed = numberOrNull(summary?.failed) ?? numberOrNull(suite?.failed);
  if (total === null) return "无数据";
  return `${passed ?? 0}/${total} 通过${failed ? ` · ${failed} 失败` : ""}`;
}

function getFailedCases(report: KnowledgeRegressionResponse): QualityFailureCaseView[] {
  const summaryCases = report.summary?.failed_cases ?? [];
  if (summaryCases.length) {
    return summaryCases.map((id) => ({
      id,
      suite: inferSuite(id),
      reason: "summary.failed_cases",
    }));
  }
  return [
    ...failedCasesFromSuite("query", report.query),
    ...failedCasesFromSuite("think", report.think),
  ];
}

function failedCasesFromSuite(
  suiteName: "query" | "think",
  suite: KnowledgeRegressionSuiteResponse | undefined,
): QualityFailureCaseView[] {
  return (suite?.cases ?? [])
    .filter((item) => item.ok === false)
    .map((item) => ({
      id: caseLabel(item),
      suite: suiteName,
      reason: item.reason || item.query || "未提供失败原因",
    }));
}

function getPreflightFailures(report: KnowledgeRegressionResponse): string[] {
  return uniqueTexts([
    ...(report.summary?.preflight_failures ?? []),
    ...(report.query?.preflight_failures ?? []),
    ...(report.think?.preflight_failures ?? []),
  ]);
}

function getWarnings(report: KnowledgeRegressionResponse): string[] {
  return uniqueTexts([
    ...(report.query?.cases ?? []).flatMap((item) => item.warnings ?? []),
    ...(report.think?.cases ?? []).flatMap((item) => item.warnings ?? []),
    report.query?.reason,
    report.think?.reason,
  ]);
}

function getTrendPoints(
  qualityReports: KnowledgeQualityReportsResponse | null | undefined,
  reports: KnowledgeRegressionResponse[],
  formatDate: FormatDate,
): QualityTrendPointView[] {
  const trendItems = (qualityReports?.trend ?? []).map((item) => trendPointFromTrendItem(item, formatDate));
  const validTrendItems = trendItems.filter((item): item is QualityTrendPointView => item !== null);
  if (validTrendItems.length >= 2) return validTrendItems.slice(0, 8);

  const derived = reports.map((item) => trendPointFromReport(item, formatDate));
  return derived.filter((item): item is QualityTrendPointView => item !== null).slice(0, 8);
}

function trendPointFromTrendItem(
  item: KnowledgeQualityReportTrendItem,
  formatDate: FormatDate,
): QualityTrendPointView | null {
  const queryPassRate = rateOrNull(item.query_pass_rate);
  const thinkPassRate = rateOrNull(item.think_pass_rate);
  if (queryPassRate === null || thinkPassRate === null) return null;
  return {
    id: item.id ?? item.ran_at ?? "report",
    label: item.ran_at ? formatDate(item.ran_at) : item.id ?? "report",
    queryPassRate,
    thinkPassRate,
    queryFailed: item.query_failed ?? 0,
    thinkFailed: item.think_failed ?? 0,
  };
}

function trendPointFromReport(
  report: KnowledgeRegressionResponse,
  formatDate: FormatDate,
): QualityTrendPointView | null {
  const queryPassRate = rateFromSuite(report.summary?.query, report.query);
  const thinkPassRate = rateFromSuite(report.summary?.think, report.think);
  if (queryPassRate === null || thinkPassRate === null) return null;
  return {
    id: report.id ?? report.ran_at,
    label: report.ran_at ? formatDate(report.ran_at) : report.id ?? "report",
    queryPassRate,
    thinkPassRate,
    queryFailed: report.summary?.query?.failed ?? report.query?.failed ?? 0,
    thinkFailed: report.summary?.think?.failed ?? report.think?.failed ?? 0,
  };
}

function rateFromSuite(
  summary: { total?: number; passed?: number } | undefined,
  suite: KnowledgeRegressionSuiteResponse | undefined,
) {
  const total = numberOrNull(summary?.total) ?? numberOrNull(suite?.total);
  const passed = numberOrNull(summary?.passed) ?? numberOrNull(suite?.passed);
  if (total === null || total <= 0 || passed === null) return null;
  return passed / total;
}

function rateOrNull(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberOrNull(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function uniqueTexts(items: Array<string | null | undefined>) {
  return Array.from(new Set(items.map((item) => item?.trim()).filter((item): item is string => Boolean(item))));
}

function caseLabel(item: KnowledgeRegressionCaseResponse) {
  return item.id || item.query || item.source_id || "unknown";
}

function inferSuite(id: string): "query" | "think" {
  return id.toLowerCase().includes("think") ? "think" : "query";
}
