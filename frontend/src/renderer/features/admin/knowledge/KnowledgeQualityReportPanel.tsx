import type { KnowledgeQualityReportsResponse } from "../../../shared/api/types";
import { buildQualityReportView } from "./qualityReportView";

export type KnowledgeQualityReportPanelProps = {
  adminLoading: boolean;
  formatDate: (value: string | number) => string;
  qualityReports: KnowledgeQualityReportsResponse | null | undefined;
  onExportQualityReport: (reportId?: string | null) => Promise<void>;
  onRunQualityReport: (includeThink?: boolean) => Promise<void>;
};

export function KnowledgeQualityReportPanel({
  adminLoading,
  formatDate,
  onExportQualityReport,
  onRunQualityReport,
  qualityReports,
}: KnowledgeQualityReportPanelProps) {
  const view = buildQualityReportView(qualityReports, formatDate);

  return (
    <div className="admin-quality-panel">
      <div className="admin-quality-header">
        <div>
          <strong>GBrain 质量报告</strong>
          <span>{view.reportCount ? `共 ${view.reportCount} 份历史报告` : "尚未生成历史报告"}</span>
        </div>
        <div className="admin-quality-actions">
          <button className="ghost-button" disabled={adminLoading} onClick={() => void onRunQualityReport(false)} type="button">
            查询质量报告
          </button>
          <button className="ghost-button" disabled={adminLoading} onClick={() => void onRunQualityReport(true)} type="button">
            Think 质量报告
          </button>
          <button
            className="ghost-button"
            disabled={adminLoading || !view.latestId}
            onClick={() => void onExportQualityReport(view.latestId)}
            type="button"
          >
            下载 JSON
          </button>
        </div>
      </div>

      <div className="admin-metric-grid admin-quality-metrics">
        <div>
          <strong>{view.statusText}</strong>
          <span>最新报告</span>
        </div>
        <div>
          <strong>{view.queryText}</strong>
          <span>Query 回归</span>
        </div>
        <div>
          <strong>{view.thinkText}</strong>
          <span>Think 回归</span>
        </div>
        <div>
          <strong>{view.failedCases.length}</strong>
          <span>失败 case</span>
        </div>
      </div>

      <div className="admin-quality-section">
        <strong>失败 case</strong>
        {view.failedCases.length ? (
          <div className="admin-list">
            {view.failedCases.slice(0, 8).map((item) => (
              <div className="admin-row admin-row-tall" key={`${item.suite}-${item.id}`}>
                <div>
                  <strong>{item.id}</strong>
                  <span>{item.suite} · {item.reason}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="admin-quality-empty">最新报告没有失败 case。</p>
        )}
      </div>

      <div className="admin-quality-section">
        <strong>warning / preflight 摘要</strong>
        {view.preflightFailures.length || view.warnings.length ? (
          <div className="admin-list">
            {view.preflightFailures.slice(0, 5).map((item) => (
              <div className="admin-row admin-row-tall" key={`preflight-${item}`}>
                <div>
                  <strong>preflight</strong>
                  <span>{item}</span>
                </div>
              </div>
            ))}
            {view.warnings.slice(0, 5).map((item) => (
              <div className="admin-row admin-row-tall" key={`warning-${item}`}>
                <div>
                  <strong>warning</strong>
                  <span>{item}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="admin-quality-empty">最新报告未返回 warning 或 preflight 失败。</p>
        )}
      </div>

      <div className="admin-quality-section">
        <strong>质量趋势</strong>
        {view.trendPoints.length >= 2 ? (
          <div className="admin-quality-trend">
            {view.trendPoints.map((item) => (
              <div className="admin-quality-trend-row" key={item.id}>
                <span>{item.label}</span>
                <div className="admin-quality-trend-bars" aria-label={`${item.label} query ${percentText(item.queryPassRate)} think ${percentText(item.thinkPassRate)}`}>
                  <div className="admin-quality-trend-track">
                    <i style={{ width: percentText(item.queryPassRate) }} />
                  </div>
                  <div className="admin-quality-trend-track is-think">
                    <i style={{ width: percentText(item.thinkPassRate) }} />
                  </div>
                </div>
                <span>Q {percentText(item.queryPassRate)} / T {percentText(item.thinkPassRate)}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="admin-quality-empty">{view.trendMessage}</p>
        )}
      </div>
    </div>
  );
}

function percentText(value: number) {
  return `${Math.round(value * 100)}%`;
}
