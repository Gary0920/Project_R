import type { GBrainStatusDashboardView } from "./gbrainStatusTypes";

export type GBrainHealthSummaryProps = {
  overall: GBrainStatusDashboardView["overall"];
};

export function GBrainHealthSummary({ overall }: GBrainHealthSummaryProps) {
  return (
    <section className={`admin-gbrain-status-summary is-${overall.level}`}>
      <div>
        <span className="admin-gbrain-status-eyebrow">Overall Health</span>
        <strong>{overall.label}</strong>
        <p>{overall.summary}</p>
      </div>
      <div className="admin-gbrain-status-basis">
        <span>更新时间：{overall.updatedAt || "-"}</span>
        {overall.basis.map((item) => <span key={item}>{item}</span>)}
      </div>
    </section>
  );
}
