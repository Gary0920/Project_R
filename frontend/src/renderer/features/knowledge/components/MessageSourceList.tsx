import { useMemo, useState } from "react";

import type { ChatContextTraceResponse, ChatSourceResponse } from "../../../shared/api/types";
import type { KnowledgeSourcePreview } from "../sourcePreview";
import { buildSourceEvidences, filterSourceEvidences, sourceEvidenceFilterLabel, visibleEvidenceFilters } from "../sourceEvidence";
import type { SourceEvidenceFilter } from "../sourceEvidenceTypes";
import { SourceEvidenceFilters } from "./SourceEvidenceFilters";
import { SourceEvidenceSummary } from "./SourceEvidenceSummary";

export type MessageSourceListProps = {
  contextTrace?: ChatContextTraceResponse | null;
  onSelectSource: (preview: KnowledgeSourcePreview) => void;
  sessionId?: number | null;
  sources?: ChatSourceResponse[] | null;
};

export function MessageSourceList({ contextTrace, onSelectSource, sessionId, sources }: MessageSourceListProps) {
  const [activeFilter, setActiveFilter] = useState<SourceEvidenceFilter>("all");
  const evidences = useMemo(() => buildSourceEvidences(sources, contextTrace), [contextTrace, sources]);
  const filters = useMemo(() => visibleEvidenceFilters(evidences), [evidences]);
  const visibleEvidences = useMemo(() => filterSourceEvidences(evidences, activeFilter), [activeFilter, evidences]);
  if (!sources?.length) return null;
  return (
    <div className="message-sources-block">
      <div className="message-sources is-compact">
        <span className="message-sources-title">引用来源：</span>
        <SourceEvidenceFilters activeFilter={activeFilter} filters={filters} onChange={setActiveFilter} />
      </div>
      <SourceEvidenceSummary evidences={evidences} />
      {visibleEvidences.length ? (
        <div className="message-sources is-compact">
          {visibleEvidences.map((evidence) => (
            <button
              className="message-source-item"
              key={evidence.id}
              onClick={() => onSelectSource({ contextTrace, index: evidence.index, source: evidence.rawSource, sessionId })}
              type="button"
            >
              <span className="message-source-index">[{evidence.index}]</span>
              <span className={`message-source-scope is-${evidence.kind}`}>{evidence.scopeLabel}</span>
              <span className={`message-source-status is-${evidence.statusLevel}`}>{evidence.statusText}</span>
              <span className="message-source-path">{evidence.locatorLabel}</span>
              <span className="message-source-file">{evidence.title}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="source-evidence-empty">
          本轮回答未引用“{sourceEvidenceFilterLabel(activeFilter)}”来源。这不代表知识库中没有相关资料，只代表本次回答没有使用该类来源。
        </div>
      )}
    </div>
  );
}
