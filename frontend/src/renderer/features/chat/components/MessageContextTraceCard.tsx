import { useState } from "react";

import type { ChatContextTraceResponse } from "../../../shared/api/types";
import { LightBulbIcon } from "../../../shared/icons/LineIcons";
import {
  buildWebSearchSummary,
  hasNonDefaultSessionPrompt,
  shouldShowContextTraceCard,
} from "../contextTraceVisibility";
import { MessageExecutionSummary } from "./MessageExecutionSummary";

export type MessageContextTraceCardProps = {
  collapseByDefault?: boolean;
  contextTrace: ChatContextTraceResponse | null | undefined;
  gbrainThinkReviewBusy?: boolean;
  messageSourceCount?: number;
  onSubmitGBrainThinkReview?: () => void;
};

type GBrainIssueSummary = {
  description: string;
  title: string;
};

function ContextTraceAudit({
  contextTrace,
  messageSourceCount = 0,
  gbrainThinkReviewBusy,
  onSubmitGBrainThinkReview,
}: {
  contextTrace: ChatContextTraceResponse;
  messageSourceCount?: number;
  gbrainThinkReviewBusy?: boolean;
  onSubmitGBrainThinkReview?: () => void;
}) {
  const attachments = contextTrace.attachments ?? [];
  const sources = contextTrace.knowledge?.sources ?? [];
  const prompt = contextTrace.prompt;
  const gbrainThink = contextTrace.gbrain_think;
  const gbrainGaps = gbrainThink?.gaps?.filter(Boolean) ?? [];
  const gbrainConflicts = gbrainThink?.conflicts?.filter(Boolean) ?? [];
  const gbrainWarnings = filterSecondaryIssues([...gbrainGaps, ...gbrainConflicts], gbrainThink?.warnings?.filter(Boolean) ?? []);
  const showKnowledgeSection = !messageSourceCount && (sources.length || contextTrace.knowledge?.source_count);
  const webSearchSummary = buildWebSearchSummary(contextTrace);

  return (
    <div className="message-context-trace-grid">
      {attachments.length ? (
        <div className="message-context-trace-section">
          <span>附件</span>
          {attachments.slice(0, 4).map((attachment) => (
            <small key={`${attachment.id}-${attachment.name}`}>{attachment.name ?? `附件 ${attachment.id}`}</small>
          ))}
          {attachments.length > 4 ? <small>另有 {attachments.length - 4} 个附件</small> : null}
        </div>
      ) : null}
      {showKnowledgeSection ? (
        <div className="message-context-trace-section">
          <span>知识来源</span>
          {sources.slice(0, 4).map((source) => (
            <small key={`${source.index}-${source.file}`}>{source.section_path || source.source_title || source.file}</small>
          ))}
          {(contextTrace.knowledge?.source_count ?? 0) > sources.length ? (
            <small>共 {contextTrace.knowledge?.source_count} 个来源</small>
          ) : null}
        </div>
      ) : null}
      {webSearchSummary ? (
        <div className="message-context-trace-section">
          <span>联网搜索</span>
          <small>检索词：{webSearchSummary.query}</small>
          <small>{webSearchSummary.providerLabel} · {webSearchSummary.resultCount} 条结果</small>
        </div>
      ) : null}
      {gbrainThink && (gbrainGaps.length || gbrainConflicts.length || gbrainWarnings.length) ? (
        <div className="message-context-trace-section is-gbrain-think">
          <div className="message-context-trace-section-header">
            <div className="message-context-trace-title">
              <span>GBrain 推理状态</span>
              <em>发现需要管理员复核的知识信号</em>
            </div>
            {onSubmitGBrainThinkReview ? (
              <button
                className="message-context-trace-action"
                disabled={gbrainThinkReviewBusy}
                onClick={onSubmitGBrainThinkReview}
                type="button"
              >
                {gbrainThinkReviewBusy ? "提交中" : "提交审核"}
              </button>
            ) : null}
          </div>
          <div className="message-context-trace-statuses">
            {gbrainConflicts.length ? <small className="is-conflict">冲突 {gbrainConflicts.length} 条</small> : null}
            {gbrainGaps.length ? <small className="is-gap">缺口 {gbrainGaps.length} 条</small> : null}
            {gbrainWarnings.length ? <small className="is-warning">警告 {gbrainWarnings.length} 条</small> : null}
          </div>
        </div>
      ) : null}
      {hasNonDefaultSessionPrompt(prompt) ? (
        <div className="message-context-trace-section">
          <span>提示词</span>
          <small>{prompt?.selected_prompt_id}</small>
          {prompt?.system_prompt_preview ? <small>{prompt.system_prompt_preview}</small> : null}
        </div>
      ) : null}
      {contextTrace.skill?.skill_name ? (
        <div className="message-context-trace-section">
          <span>Skill</span>
          <small>{contextTrace.skill.display_name || contextTrace.skill.skill_name}</small>
        </div>
      ) : null}
    </div>
  );
}

function buildGBrainIssueSummary(conflicts: string[], gaps: string[], warnings: string[]): GBrainIssueSummary | null {
  const issue = conflicts[0] || gaps[0] || warnings[0];
  if (!issue) return null;
  let title = "发现需复核提示";
  if (conflicts.length && gaps.length) title = "发现知识冲突与缺口";
  else if (conflicts.length) title = "发现知识冲突";
  else if (gaps.length) title = "发现知识缺口";
  return {
    description: `GBrain 提示：${issue}`,
    title,
  };
}

function GBrainInlineFeedback({
  busy,
  onDismiss,
  onSubmit,
  summary,
}: {
  busy?: boolean;
  onDismiss: () => void;
  onSubmit?: () => void;
  summary: GBrainIssueSummary;
}) {
  return (
    <div className="message-gbrain-feedback">
      <div className="message-gbrain-feedback-icon" aria-hidden>
        <LightBulbIcon />
      </div>
      <div className="message-gbrain-feedback-copy">
        <strong>{summary.title}</strong>
        <span>{summary.description}</span>
      </div>
      <div className="message-gbrain-feedback-actions">
        <button className="message-gbrain-feedback-ignore" onClick={onDismiss} type="button">
          忽略
        </button>
        {onSubmit ? (
          <button className="message-gbrain-feedback-submit" disabled={busy} onClick={onSubmit} type="button">
            {busy ? "提交中" : "提交审核"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function filterSecondaryIssues(primary: string[], secondary: string[]) {
  const primaryKeys = new Set(primary.map(issueKey).filter(Boolean));
  return secondary.filter((item) => {
    const key = issueKey(item);
    return key && !primaryKeys.has(key);
  });
}

function issueKey(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s。．.，,、；;：:！!？?（）()[\]【】"'`_-]/g, "");
}

export function MessageContextTraceCard({
  collapseByDefault = false,
  contextTrace,
  gbrainThinkReviewBusy,
  messageSourceCount = 0,
  onSubmitGBrainThinkReview,
}: MessageContextTraceCardProps) {
  const [gbrainFeedbackHidden, setGbrainFeedbackHidden] = useState(false);
  if (!shouldShowContextTraceCard(contextTrace, messageSourceCount) || !contextTrace) return null;

  const attachments = contextTrace.attachments ?? [];
  const sourceCount = contextTrace.knowledge?.source_count ?? contextTrace.knowledge?.sources?.length ?? 0;
  const gbrainThink = contextTrace.gbrain_think;
  const gbrainGaps = gbrainThink?.gaps?.filter(Boolean) ?? [];
  const gbrainConflicts = gbrainThink?.conflicts?.filter(Boolean) ?? [];
  const gbrainWarnings = filterSecondaryIssues([...gbrainGaps, ...gbrainConflicts], gbrainThink?.warnings?.filter(Boolean) ?? []);
  const gbrainIssueSummary = buildGBrainIssueSummary(gbrainConflicts, gbrainGaps, gbrainWarnings);
  const webSearchSummary = buildWebSearchSummary(contextTrace);
  const hasKnowledgeTrace = messageSourceCount <= 0 && Boolean(sourceCount);
  const hasOnlyGBrainFeedback = Boolean(
    gbrainIssueSummary
    && !attachments.length
    && !hasKnowledgeTrace
    && !webSearchSummary
    && !hasNonDefaultSessionPrompt(contextTrace.prompt)
    && !contextTrace.skill?.skill_name,
  );

  if (hasOnlyGBrainFeedback && gbrainIssueSummary) {
    if (gbrainFeedbackHidden) return null;
    return (
      <div className="message-inline-feedback-stack">
        <div className="message-inline-feedback-divider" />
        <GBrainInlineFeedback
          busy={gbrainThinkReviewBusy}
          onDismiss={() => setGbrainFeedbackHidden(true)}
          onSubmit={onSubmitGBrainThinkReview}
          summary={gbrainIssueSummary}
        />
        <div className="message-inline-feedback-divider" />
      </div>
    );
  }

  const audit = (
    <ContextTraceAudit
      contextTrace={contextTrace}
      gbrainThinkReviewBusy={gbrainThinkReviewBusy}
      messageSourceCount={messageSourceCount}
      onSubmitGBrainThinkReview={onSubmitGBrainThinkReview}
    />
  );

  if (collapseByDefault && !onSubmitGBrainThinkReview) {
    const parts = [
      attachments.length ? `附件 ${attachments.length}` : null,
      sourceCount ? `来源 ${sourceCount}` : null,
    ].filter(Boolean);
    return (
      <MessageExecutionSummary
        contextMeta={parts.length ? parts.join(" · ") : undefined}
        hasAttachments={attachments.length > 0}
        kind="context"
        status="completed"
        title=""
      >
        {audit}
      </MessageExecutionSummary>
    );
  }

  return (
    <div className="message-context-trace">
      <div className="message-context-trace-header">
        <strong>本轮上下文</strong>
      </div>
      {audit}
    </div>
  );
}
