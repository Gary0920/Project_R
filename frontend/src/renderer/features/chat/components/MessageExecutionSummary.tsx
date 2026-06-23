import { useState, type ReactNode } from "react";
import {
  AgentIcon,
  BrainIcon,
  ChevronDownIcon,
  PaperclipIcon,
  PromptIcon,
} from "../../../shared/icons/LineIcons";

export type ExecutionSummaryKind = "skill" | "agent" | "context";

export type MessageExecutionSummaryProps = {
  kind: ExecutionSummaryKind;
  title: string;
  stepCount?: number;
  status: string;
  defaultExpanded?: boolean;
  /** Full-line fallback when structured fields are insufficient */
  summaryText?: string;
  /** Extra meta for context rows, e.g. "附件 2 · 来源 3" */
  contextMeta?: string;
  hasAttachments?: boolean;
  children: ReactNode;
};

function kindLabel(kind: ExecutionSummaryKind) {
  if (kind === "skill") return "已运行 Skill";
  if (kind === "agent") return "Agent";
  return "本轮上下文";
}

function statusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "running") return "执行中";
  if (status === "waiting") return "等待输入";
  if (status === "queued") return "排队中";
  if (status === "cancelled") return "已取消";
  return status;
}

export function sanitizeAgentSummaryTitle(title: string) {
  const trimmed = title.trim();
  if (trimmed.startsWith("运行 Skill:")) {
    return trimmed.slice("运行 Skill:".length).trim();
  }
  if (trimmed.startsWith("运行 Skill：")) {
    return trimmed.slice("运行 Skill：".length).trim();
  }
  return trimmed || "Agent 任务";
}

function displayTitle(kind: ExecutionSummaryKind, title: string) {
  if (kind === "agent") return sanitizeAgentSummaryTitle(title);
  return title.trim();
}

function SummaryIcon({ hasAttachments, kind }: { hasAttachments?: boolean; kind: ExecutionSummaryKind }) {
  if (kind === "skill") return <PromptIcon className="message-execution-summary-icon-svg" />;
  if (kind === "agent") return <AgentIcon className="message-execution-summary-icon-svg" />;
  if (hasAttachments) return <PaperclipIcon className="message-execution-summary-icon-svg" />;
  return <BrainIcon className="message-execution-summary-icon-svg" />;
}

function buildMetaParts(stepCount: number | undefined, status: string, contextMeta?: string) {
  const parts: string[] = [];
  if (contextMeta) parts.push(contextMeta);
  if (stepCount != null && stepCount > 0) parts.push(`${stepCount} 个步骤`);
  parts.push(statusLabel(status));
  return parts.join(" · ");
}

export function MessageExecutionSummary({
  kind,
  title,
  stepCount,
  status,
  defaultExpanded = false,
  summaryText,
  contextMeta,
  hasAttachments,
  children,
}: MessageExecutionSummaryProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const resolvedTitle = displayTitle(kind, title);
  const meta = buildMetaParts(stepCount, status, contextMeta);
  const useFallback = Boolean(summaryText);

  return (
    <div className="message-execution-summary">
      <button
        aria-expanded={expanded}
        className="message-execution-summary-trigger"
        onClick={() => setExpanded((value) => !value)}
        type="button"
      >
        <span aria-hidden className="message-execution-summary-icon">
          <SummaryIcon hasAttachments={hasAttachments} kind={kind} />
        </span>
        {useFallback ? (
          <span className="message-execution-summary-text">{summaryText}</span>
        ) : (
          <span className="message-execution-summary-copy">
            <span className="message-execution-summary-kind">{kindLabel(kind)}</span>
            {resolvedTitle ? (
              <span className="message-execution-summary-title">{resolvedTitle}</span>
            ) : null}
            <span className="message-execution-summary-meta">{meta}</span>
          </span>
        )}
        <ChevronDownIcon
          aria-hidden
          className={`message-execution-summary-chevron ${expanded ? "is-expanded" : ""}`}
        />
      </button>
      <div className={`message-execution-audit-shell ${expanded ? "is-expanded" : ""}`}>
        <div className="message-execution-audit-inner">
          <div className="message-execution-audit">{children}</div>
        </div>
      </div>
    </div>
  );
}
