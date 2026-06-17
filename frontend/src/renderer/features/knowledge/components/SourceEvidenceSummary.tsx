import type { SourceEvidence } from "../sourceEvidenceTypes";

export type SourceEvidenceSummaryProps = {
  evidences: SourceEvidence[];
};

export function SourceEvidenceSummary({ evidences }: SourceEvidenceSummaryProps) {
  if (!evidences.length) return null;
  const kinds = Array.from(new Set(evidences.map((item) => item.scopeLabel))).join("、");
  const issueCount = evidences.reduce((count, item) => count + item.issues.length, 0);
  const limitedCount = evidences.filter((item) => item.statusLevel === "limited").length;
  return (
    <div className="source-evidence-summary">
      <span>本轮引用 {evidences.length} 个来源</span>
      <span>{kinds}</span>
      {limitedCount ? <span>{limitedCount} 个定位有限</span> : null}
      {issueCount ? <span>{issueCount} 条风险提示</span> : null}
    </div>
  );
}
