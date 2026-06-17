import type { SourceEvidence } from "../sourceEvidenceTypes";

export type SourceEvidencePanelProps = {
  compact?: boolean;
  evidence: SourceEvidence;
};

const ISSUE_LABELS = {
  conflict: "冲突",
  gap: "缺口",
  warning: "警告",
};

export function SourceEvidencePanel({ compact = false, evidence }: SourceEvidencePanelProps) {
  const showMeta = !compact;
  return (
    <section className={`source-evidence-panel is-${evidence.statusLevel}`} aria-label="证据说明">
      <div className="source-evidence-panel-header">
        <strong>证据说明</strong>
        <span>{evidence.statusText}</span>
      </div>
      {showMeta ? (
        <dl className="source-evidence-meta">
          <div>
            <dt>来源范围</dt>
            <dd>{evidence.scopeLabel}</dd>
          </div>
          <div>
            <dt>定位</dt>
            <dd>{evidence.locatorLabel}</dd>
          </div>
        </dl>
      ) : null}
      {evidence.issues.length ? (
        <div className="source-evidence-issues">
          {evidence.issues.slice(0, 4).map((issue, index) => (
            <p className={`is-${issue.kind}`} key={`${issue.kind}-${index}`}>
              <strong>{ISSUE_LABELS[issue.kind]}</strong>
              <span>{issue.text}</span>
            </p>
          ))}
        </div>
      ) : null}
      <ul className="source-evidence-limitations">
        {evidence.limitations.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </section>
  );
}
