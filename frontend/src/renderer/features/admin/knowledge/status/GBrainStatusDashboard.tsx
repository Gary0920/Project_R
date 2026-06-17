import type { GBrainMaintenanceResponse, KnowledgeStatusResponse } from "../../../../shared/api/types";
import { GBrainHealthSummary } from "./GBrainHealthSummary";
import { GBrainSignalCards } from "./GBrainSignalCards";
import { GBrainWarningList } from "./GBrainWarningList";
import { buildGBrainStatusDashboardView } from "./gbrainStatusView";
import type { GBrainMaintenanceEntry } from "./gbrainStatusTypes";

export type GBrainStatusDashboardProps = {
  adminLoading: boolean;
  formatDate: (value: string | number) => string;
  knowledgeStatus: KnowledgeStatusResponse | null;
  maintenance: GBrainMaintenanceResponse | null;
  onGoQuality: () => void;
  onMaintenanceCheck: () => Promise<void>;
  onPollCitationFixer: () => Promise<void>;
  onRefresh: () => Promise<void>;
};

export function GBrainStatusDashboard({
  adminLoading,
  formatDate,
  knowledgeStatus,
  maintenance,
  onGoQuality,
  onMaintenanceCheck,
  onPollCitationFixer,
  onRefresh,
}: GBrainStatusDashboardProps) {
  const view = buildGBrainStatusDashboardView(knowledgeStatus, maintenance, formatDate);

  return (
    <div className="admin-gbrain-status-dashboard">
      <GBrainHealthSummary overall={view.overall} />
      <GBrainSignalCards signals={view.signals} />
      <GBrainWarningList warnings={view.warnings} />
      <section className="admin-gbrain-status-section">
        <header>
          <strong>Maintenance Entry Points</strong>
          <span>使用现有维护能力处理上方问题</span>
        </header>
        <div className="admin-gbrain-status-entry-grid">
          {view.entries.map((entry) => (
            <article className="admin-gbrain-status-entry" key={entry.id}>
              <div>
                <strong>{entry.label}</strong>
                <span>{entry.detail}</span>
              </div>
              {entry.kind !== "reference" ? (
                <button className="ghost-button" disabled={adminLoading} onClick={() => void runEntry(entry, {
                  onGoQuality,
                  onMaintenanceCheck,
                  onPollCitationFixer,
                  onRefresh,
                })} type="button">
                  {entry.actionLabel ?? "查看"}
                </button>
              ) : (
                <span className="admin-gbrain-status-reference">见下方</span>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function runEntry(
  entry: GBrainMaintenanceEntry,
  actions: Pick<GBrainStatusDashboardProps, "onGoQuality" | "onMaintenanceCheck" | "onPollCitationFixer" | "onRefresh">,
) {
  if (entry.id === "refresh") return actions.onRefresh();
  if (entry.id === "maintenance-check") return actions.onMaintenanceCheck();
  if (entry.id === "quality") return actions.onGoQuality();
  if (entry.id === "citation-fixer") return actions.onPollCitationFixer();
  return undefined;
}
