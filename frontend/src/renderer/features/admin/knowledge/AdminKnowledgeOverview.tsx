import type { KnowledgeStatusResponse } from "../../../shared/api/types";
import { KnowledgeQualityReportPanel } from "./KnowledgeQualityReportPanel";
import { knowledgeStatusMetrics } from "./knowledgeAdminView";

export type AdminKnowledgeOverviewProps = {
  adminLoading: boolean;
  formatDate: (value: string | number) => string;
  knowledgeStatus: KnowledgeStatusResponse | null;
  statusLabel: (value?: string | null) => string;
  yesNo: (value?: boolean | null) => string;
  onExportQualityReport: (reportId?: string | null) => Promise<void>;
  onRefreshKnowledge: (enablePdfStructuredExtraction?: boolean) => Promise<void>;
  onRestartGBrain: () => Promise<void>;
  onRunQualityReport: (includeThink?: boolean) => Promise<void>;
  onStartGBrain: () => Promise<void>;
};

export function AdminKnowledgeOverview({
  adminLoading,
  formatDate,
  knowledgeStatus,
  onExportQualityReport,
  onRefreshKnowledge,
  onRestartGBrain,
  onRunQualityReport,
  onStartGBrain,
  statusLabel,
  yesNo,
}: AdminKnowledgeOverviewProps) {
  const readinessErrors = knowledgeStatus?.readiness?.errors ?? [];
  const doctorWarnings = knowledgeStatus?.doctor?.warning_or_failed_checks ?? [];

  return (
    <div className="settings-section admin-gbrain-panel">
      <div className="settings-section-header">
        <h3>GBrain 知识库</h3>
        <p>company-wiki source 与本机 embedding 状态</p>
      </div>
      <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
        {knowledgeStatusMetrics(knowledgeStatus, statusLabel, yesNo).map((metric) => (
          <div key={metric.label}>
            <strong>{metric.value}</strong>
            <span>{metric.label}</span>
          </div>
        ))}
      </div>

      {readinessErrors.length ? (
        <div className="admin-list" style={{ marginBottom: 12 }}>
          {readinessErrors.map((item) => (
            <div className="admin-row" key={item}>
              <div>
                <strong>待处理</strong>
                <span>{item}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {doctorWarnings.length ? (
        <div className="admin-list" style={{ marginBottom: 12 }}>
          {doctorWarnings.map((item) => (
            <div className="admin-row" key={`${item.name}-${item.message}`}>
              <div>
                <strong>{item.name ?? "doctor"}</strong>
                <span>{statusLabel(item.status)} · {item.message}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <KnowledgeQualityReportPanel
        adminLoading={adminLoading}
        formatDate={formatDate}
        onExportQualityReport={onExportQualityReport}
        onRunQualityReport={onRunQualityReport}
        qualityReports={knowledgeStatus?.quality_reports}
      />

      <div className="admin-gbrain-actions">
        <button className="ghost-button" onClick={() => void onStartGBrain()} type="button">
          启动 GBrain
        </button>
        <button className="ghost-button" onClick={() => void onRestartGBrain()} type="button">
          重启 GBrain
        </button>
        <button className="ghost-button" onClick={() => void onRefreshKnowledge()} type="button">
          导入 raw 并同步
        </button>
        <button className="ghost-button" onClick={() => void onRefreshKnowledge(true)} type="button">
          含 PDF 提炼
        </button>
      </div>
    </div>
  );
}
