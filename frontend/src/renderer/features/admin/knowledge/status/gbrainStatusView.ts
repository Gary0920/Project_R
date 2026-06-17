import type { GBrainMaintenanceResponse, KnowledgeStatusResponse } from "../../../../shared/api/types";
import { buildQualityReportView } from "../qualityReportView";
import type {
  GBrainMaintenanceEntry,
  GBrainOverallLevel,
  GBrainSignalCard,
  GBrainStatusDashboardView,
  GBrainWarningItem,
} from "./gbrainStatusTypes";

const LEVEL_LABEL: Record<GBrainOverallLevel, string> = {
  critical: "异常",
  attention: "需关注",
  ok: "正常",
  unknown: "未知",
};

type FormatDate = (value: string | number) => string;

export function buildGBrainStatusDashboardView(
  knowledgeStatus: KnowledgeStatusResponse | null,
  maintenance: GBrainMaintenanceResponse | null,
  formatDate: FormatDate,
): GBrainStatusDashboardView {
  const signals = buildSignals(knowledgeStatus, maintenance, formatDate);
  const warnings = buildWarnings(knowledgeStatus, maintenance, signals);
  const overallLevel = pickOverallLevel(knowledgeStatus, maintenance, signals, warnings);
  return {
    overall: {
      level: overallLevel,
      label: LEVEL_LABEL[overallLevel],
      summary: overallSummary(overallLevel),
      basis: overallBasis(knowledgeStatus, maintenance, signals, warnings),
      updatedAt: maintenance?.ran_at ? formatDate(maintenance.ran_at) : formatOptional(knowledgeStatus?.last_sync, formatDate),
    },
    signals,
    warnings,
    entries: maintenanceEntries(),
  };
}

function buildSignals(
  knowledgeStatus: KnowledgeStatusResponse | null,
  maintenance: GBrainMaintenanceResponse | null,
  formatDate: FormatDate,
): GBrainSignalCard[] {
  const doctorSummary = record(maintenance?.doctor_summary) ?? record(knowledgeStatus?.doctor);
  const healthScore = numberValue(doctorSummary, "health_score") ?? numberValue(knowledgeStatus?.doctor, "health_score");
  const worker = maintenance?.dream_cycle_worker;
  const jobsStatus = toolStatus(maintenance?.jobs);
  const quality = buildQualityReportView(knowledgeStatus?.quality_reports, formatDate);
  const latestQuality = knowledgeStatus?.quality_reports?.latest ?? null;

  return [
    {
      id: "doctor",
      label: "Doctor",
      status: signalFromTool(maintenance?.doctor, healthScore),
      value: healthScore == null ? toolStatus(maintenance?.doctor) : String(healthScore),
      detail: healthScore == null ? "未返回 health_score" : `health_score ${healthScore}`,
    },
    {
      id: "worker",
      label: "Worker",
      status: workerStatus(worker),
      value: worker ? (worker.running ? "运行中" : "未运行") : "未知",
      detail: worker
        ? `心跳 ${formatOptional(worker.last_heartbeat_at, formatDate)}${worker.last_error ? ` · 最近错误 ${worker.last_error}` : ""}`
        : "未返回 worker 状态",
    },
    {
      id: "jobs",
      label: "Jobs",
      status: jobsStatus === "ok" ? "ok" : jobsStatus === "unknown" ? "unknown" : "critical",
      value: jobsStatus,
      detail: `最近任务 ${resultArray(maintenance?.jobs).length} 个`,
    },
    {
      id: "quality",
      label: "Quality",
      status: !latestQuality ? "unknown" : latestQuality.ok ? "ok" : "attention",
      value: latestQuality ? (latestQuality.ok ? "通过" : "有失败") : "无报告",
      detail: quality.latest ? `${quality.queryText} / ${quality.thinkText}` : "尚未生成质量报告",
    },
  ];
}

function buildWarnings(
  knowledgeStatus: KnowledgeStatusResponse | null,
  maintenance: GBrainMaintenanceResponse | null,
  signals: GBrainSignalCard[],
): GBrainWarningItem[] {
  const warnings: GBrainWarningItem[] = [];
  if (!knowledgeStatus && !maintenance) {
    warnings.push({
      id: "missing-sources",
      level: "unknown",
      title: "状态源缺失",
      detail: "尚未取得 knowledge status 或 GBrain maintenance 数据。",
      action: "刷新管理员数据或检查后端连接。",
    });
    return warnings;
  }

  if (maintenance?.ok === false) {
    warnings.push({
      id: "maintenance-not-ok",
      level: "critical",
      title: "维护状态未通过",
      detail: "G7.0 MVP 暂将 maintenance.ok=false 视为 critical。",
      action: "进入 GBrain 维护操作区运行维护检查。",
    });
  }

  for (const signal of signals) {
    if (signal.status === "critical") {
      warnings.push({
        id: `signal-${signal.id}`,
        level: "critical",
        title: `${signal.label} 异常`,
        detail: signal.detail,
        action: entryActionForSignal(signal.id),
      });
    } else if (signal.status === "attention") {
      warnings.push({
        id: `signal-${signal.id}`,
        level: "attention",
        title: `${signal.label} 需关注`,
        detail: signal.detail,
        action: entryActionForSignal(signal.id),
      });
    }
  }

  for (const item of knowledgeStatus?.readiness?.errors ?? []) {
    warnings.push({
      id: `readiness-${item}`,
      level: "critical",
      title: "Readiness 错误",
      detail: item,
      action: "查看 GBrain 知识库概览或维护区。",
    });
  }

  for (const item of knowledgeStatus?.readiness?.warnings ?? []) {
    warnings.push({
      id: `readiness-warning-${item}`,
      level: "attention",
      title: "Readiness 提醒",
      detail: item,
      action: "查看 GBrain 知识库概览或维护区。",
    });
  }

  const citationJobs = maintenance?.citation_fixer_jobs?.tracked_jobs ?? [];
  if (citationJobs.length) {
    warnings.push({
      id: "citation-fixer-tracked",
      level: "attention",
      title: "Citation-fixer 有跟踪任务",
      detail: `当前跟踪 ${citationJobs.length} 个任务。`,
      action: "轮询 citation-fixer 或查看下方任务列表。",
    });
  }

  const flagged = numberValue(record(maintenance?.contradiction_probe?.last_summary), "total_contradictions_flagged");
  if (flagged && flagged > 0) {
    warnings.push({
      id: "contradiction-flagged",
      level: "attention",
      title: "发现疑似冲突",
      detail: `Contradiction probe 标记 ${flagged} 条疑似冲突。`,
      action: "查看下方 contradiction 记录。",
    });
  }

  return dedupeWarnings(warnings);
}

function pickOverallLevel(
  knowledgeStatus: KnowledgeStatusResponse | null,
  maintenance: GBrainMaintenanceResponse | null,
  signals: GBrainSignalCard[],
  warnings: GBrainWarningItem[],
): GBrainOverallLevel {
  if (!knowledgeStatus && !maintenance) return "unknown";
  if (warnings.some((item) => item.level === "critical") || signals.some((item) => item.status === "critical")) return "critical";
  if (warnings.some((item) => item.level === "attention") || signals.some((item) => item.status === "attention")) return "attention";
  return "ok";
}

function overallSummary(level: GBrainOverallLevel) {
  if (level === "critical") return "存在需要管理员立即处理的 GBrain 异常。";
  if (level === "attention") return "核心服务可用，但存在需要关注的维护信号。";
  if (level === "ok") return "关键状态源未发现明显异常。";
  return "缺少关键状态源，暂无法判断 GBrain 健康状态。";
}

function overallBasis(
  knowledgeStatus: KnowledgeStatusResponse | null,
  maintenance: GBrainMaintenanceResponse | null,
  signals: GBrainSignalCard[],
  warnings: GBrainWarningItem[],
) {
  if (!knowledgeStatus && !maintenance) return ["knowledge status 和 maintenance 均未返回。"];
  const critical = warnings.filter((item) => item.level === "critical").length;
  const attention = warnings.filter((item) => item.level === "attention").length;
  return [
    `critical ${critical} 条，attention ${attention} 条。`,
    `signals: ${signals.map((item) => `${item.label}=${LEVEL_LABEL[item.status]}`).join(" / ")}`,
  ];
}

function maintenanceEntries(): GBrainMaintenanceEntry[] {
  return [
    { id: "refresh", label: "刷新状态", detail: "重新读取 GBrain maintenance 状态。", actionLabel: "刷新", kind: "button" },
    { id: "maintenance-check", label: "维护检查", detail: "运行现有 maintain/onboard check。", actionLabel: "运行检查", kind: "button" },
    { id: "quality", label: "质量报告", detail: "返回概览页查看 G5 质量报告。", actionLabel: "查看质量报告", kind: "button" },
    { id: "citation-fixer", label: "Citation-fixer", detail: "轮询已有 citation-fixer 跟踪任务。", actionLabel: "轮询", kind: "button" },
    { id: "operations", label: "维护操作区", detail: "继续使用下方现有 Dream / contradiction / graph / jobs 操作。", kind: "reference" },
  ];
}

function signalFromTool(tool: unknown, healthScore?: number | null): GBrainOverallLevel {
  const status = toolStatus(tool);
  if (status !== "ok" && status !== "unknown") return "critical";
  if (typeof healthScore === "number" && healthScore < 90) return "attention";
  return status === "ok" ? "ok" : "unknown";
}

function workerStatus(worker: GBrainMaintenanceResponse["dream_cycle_worker"]): GBrainOverallLevel {
  if (!worker) return "unknown";
  if (worker.last_error?.trim()) return "critical";
  if (!worker.running) return "attention";
  return "ok";
}

function toolStatus(tool: unknown) {
  const value = record(tool);
  const status = String(value?.status ?? (value?.ok === true ? "ok" : value?.ok === false ? "failed" : "unknown"));
  return status.trim() || "unknown";
}

function entryActionForSignal(id: GBrainSignalCard["id"]) {
  if (id === "doctor") return "运行维护检查或查看 doctor 输出。";
  if (id === "worker") return "查看 Worker 卡片，必要时重启 Worker。";
  if (id === "jobs") return "查看下方 jobs 列表或刷新状态。";
  return "查看质量报告摘要。";
}

function formatOptional(value: string | number | null | undefined, formatDate: FormatDate) {
  if (value == null || value === "") return "-";
  return formatDate(value);
}

function resultArray(tool: unknown) {
  const value = record(tool);
  const result = value?.result;
  if (Array.isArray(result)) return result;
  if (record(result) && Array.isArray(record(result)?.items)) return record(result)?.items as unknown[];
  if (record(result) && Array.isArray(record(result)?.jobs)) return record(result)?.jobs as unknown[];
  return [];
}

function numberValue(value: unknown, key: string) {
  const payload = record(value);
  const raw = payload?.[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function dedupeWarnings(items: GBrainWarningItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}
