import { GBrainStatusDashboard } from "../knowledge/status/GBrainStatusDashboard";
import type { AdminSettingsPanelController } from "./AdminSettingsPanel";

type AdminGBrainSectionProps = {
  controller: AdminSettingsPanelController;
};

export function AdminGBrainSection({ controller }: AdminGBrainSectionProps) {
  const {
    adminLoading, citationFixerDraft, formatDate, formatOptionalDate, gbrainContradictionDraft, gbrainDreamDraft,
    gbrainEntityMerge, gbrainEntityMergePreview, gbrainGraph, gbrainGraphDraft, gbrainMaintenance, handleApplyGBrainEntityMergeCandidate,
    handleCancelGBrainJob, handleGBrainMaintenanceCheck, handleLoadGBrainEntityMergeCandidates, handleLoadGBrainGraph,
    handlePollGBrainCitationFixerJobs, handlePollGBrainDreamCycleJobs, handlePreviewGBrainEntityMergeCandidate,
    handleRefreshGBrainMaintenance, handleRestartGBrainDreamCycleWorker, handleRetryGBrainJob, handleRollbackGBrainCitationFixerJob,
    handleRunGBrainContradictionProbe, handleRunGBrainDreamCycle, handleSaveGBrainContradictionProbe, handleSaveGBrainDreamCycle,
    handleSubmitCitationFixer, handleSubmitGBrainJob, handleTickGBrainContradictionProbe, handleTickGBrainDreamCycle,
    knowledgeStatus, recordNumber, recordText, setAdminTab, setCitationFixerDraft, setGBrainContradictionDraft, setGBrainDreamDraft,
    setGBrainGraphDraft, shortValue, statusLabel, toolResultArray, toolStatus, asRecord,
  } = controller;

  return (
                  <div className="settings-section admin-gbrain-panel">
                    <div className="settings-section-header">
                      <div>
                        <h3>GBrain 维护</h3>
                        <p>doctor、maintain check、jobs 与 contradiction 的管理员入口</p>
                      </div>
                    </div>
                    <GBrainStatusDashboard
                      adminLoading={adminLoading}
                      formatDate={formatDate}
                      knowledgeStatus={knowledgeStatus}
                      maintenance={gbrainMaintenance}
                      onGoQuality={() => setAdminTab("overview")}
                      onMaintenanceCheck={handleGBrainMaintenanceCheck}
                      onPollCitationFixer={handlePollGBrainCitationFixerJobs}
                      onRefresh={handleRefreshGBrainMaintenance}
                    />
                    {(() => {
                      const doctorSummary = asRecord(gbrainMaintenance?.doctor_summary);
                      const agentStatus = asRecord(gbrainMaintenance?.agent);
                      const jobs = toolResultArray(gbrainMaintenance?.jobs);
                      const contradictions = toolResultArray(gbrainMaintenance?.contradictions, "contradictions");
                      const healthScore = recordNumber(doctorSummary, "health_score");
                      const citationFixerJobs = gbrainMaintenance?.citation_fixer_jobs?.tracked_jobs ?? [];
                      const citationFixerRecentJobs = citationFixerJobs.slice(-5).reverse();
                      const maintenanceWorker = gbrainMaintenance?.dream_cycle_worker;
                      const workerTick = asRecord(maintenanceWorker?.last_tick_result);
                      const workerPoll = asRecord(maintenanceWorker?.last_poll_result);
                      const citationWorkerPoll = asRecord(maintenanceWorker?.last_citation_fixer_poll_result);
                      const contradictionProbe = gbrainMaintenance?.contradiction_probe;
                      const contradictionSummary = asRecord(contradictionProbe?.last_summary);
                      const contradictionWorkerProbe = asRecord(maintenanceWorker?.last_contradiction_probe_result);
                      const workerError = maintenanceWorker?.last_error?.trim() ?? "";
                      const graphNodeTitleById = new Map((gbrainGraph?.nodes ?? []).map((node) => [node.id, node.title]));
                      const graphNodes = (gbrainGraph?.nodes ?? []).slice(0, 12);
                      const graphEdges = (gbrainGraph?.edges ?? []).slice(0, 12);
                      const graphEvents = (gbrainGraph?.events ?? []).slice(0, 8);
                      const entityMergeCandidates = (gbrainEntityMerge?.candidates ?? []).slice(0, 12);
                      return (
                        <>
                          <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                            <div>
                              <strong>{gbrainMaintenance?.ok ? "正常" : "需检查"}</strong>
                              <span>维护状态</span>
                            </div>
                            <div>
                              <strong>{healthScore ?? "-"}</strong>
                              <span>doctor 分数</span>
                            </div>
                            <div>
                              <strong>{toolStatus(gbrainMaintenance?.jobs)}</strong>
                              <span>jobs 接口</span>
                            </div>
                            <div>
                              <strong>{jobs.length}</strong>
                              <span>最近任务</span>
                            </div>
                            <div>
                              <strong>{toolStatus(gbrainMaintenance?.contradictions)}</strong>
                              <span>冲突检测</span>
                            </div>
                            <div>
                              <strong>{contradictions.length}</strong>
                              <span>冲突记录</span>
                            </div>
                            <div>
                              <strong>{toolStatus(gbrainMaintenance?.onboard_check)}</strong>
                              <span>maintain check</span>
                            </div>
                            <div>
                              <strong>{statusLabel(recordText(agentStatus, "status"))}</strong>
                              <span>agent OAuth</span>
                            </div>
                            <div>
                              <strong>{gbrainMaintenance?.ran_at ? formatDate(gbrainMaintenance.ran_at) : "-"}</strong>
                              <span>更新时间</span>
                            </div>
                          </div>

                          <div className="admin-gbrain-actions">
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRefreshGBrainMaintenance()} type="button">
                              刷新状态
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleGBrainMaintenanceCheck()} type="button">
                              维护检查
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("sync")} type="button">
                              提交 sync
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("embed")} type="button">
                              提交 embed
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("lint")} type="button">
                              lint 预检
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitGBrainJob("backlinks")} type="button">
                              backlinks 检查
                            </button>
                          </div>

                          <div className="admin-maintenance-form admin-maintenance-form-dream">
                            <label className="admin-maintenance-toggle">
                              <input
                                checked={gbrainDreamDraft.enabled}
                                onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, enabled: event.target.checked }))}
                                type="checkbox"
                              />
                              启用
                            </label>
                            <input
                              inputMode="numeric"
                              placeholder="间隔小时"
                              value={gbrainDreamDraft.intervalHours}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, intervalHours: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="目标分"
                              value={gbrainDreamDraft.targetScore}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, targetScore: event.target.value }))}
                            />
                            <input
                              placeholder="source id"
                              value={gbrainDreamDraft.sourceId}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, sourceId: event.target.value }))}
                            />
                            <input
                              placeholder="jobs，逗号分隔"
                              value={gbrainDreamDraft.jobNames}
                              onChange={(event) => setGBrainDreamDraft((prev) => ({ ...prev, jobNames: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSaveGBrainDreamCycle()} type="button">
                              保存 Dream
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRunGBrainDreamCycle()} type="button">
                              立即运行
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleTickGBrainDreamCycle()} type="button">
                              检查到期
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handlePollGBrainDreamCycleJobs()} type="button">
                              轮询任务
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRestartGBrainDreamCycleWorker()} type="button">
                              重启 Worker
                            </button>
                          </div>

                          <div className="admin-list" style={{ marginBottom: 12 }}>
                            <div className="admin-row">
                              <div>
                                <strong>Dream Cycle</strong>
                                <span>
                                  {`状态 ${gbrainMaintenance?.dream_cycle?.enabled ? "启用" : "停用"} · 上次 ${gbrainMaintenance?.dream_cycle?.last_run_at ? formatDate(gbrainMaintenance.dream_cycle.last_run_at) : "-"} · 下次 ${gbrainMaintenance?.dream_cycle?.next_run_at ? formatDate(gbrainMaintenance.dream_cycle.next_run_at) : "-"} · 跟踪任务 ${gbrainMaintenance?.dream_cycle?.tracked_jobs?.length ?? 0} · 最近轮询 ${gbrainMaintenance?.dream_cycle?.last_job_poll_at ? formatDate(gbrainMaintenance.dream_cycle.last_job_poll_at) : "-"} · Worker ${maintenanceWorker?.running ? "运行中" : "未运行"} · 心跳 ${maintenanceWorker?.last_heartbeat_at ? formatDate(maintenanceWorker.last_heartbeat_at) : "-"}`}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className={`admin-maintenance-card ${workerError ? "is-warning" : ""}`}>
                            <div>
                              <strong>GBrain Worker</strong>
                              <span>
                                {`状态 ${maintenanceWorker?.running ? "运行中" : "未运行"} · 配置 ${maintenanceWorker?.enabled ? "启用" : "停用"} · 间隔 ${maintenanceWorker?.interval_seconds ?? "-"}s · 次数 ${maintenanceWorker?.run_count ?? 0} · 心跳 ${formatOptionalDate(maintenanceWorker?.last_heartbeat_at)}`}
                              </span>
                            </div>
                            {workerError ? <p>{`最近错误：${workerError}`}</p> : <p>最近错误：无</p>}
                            <p>
                              {[
                                `Dream tick ${recordText(workerTick, "status") || "-"}`,
                                `Dream poll ${recordText(workerPoll, "status") || "-"} / ${shortValue(recordNumber(workerPoll, "checked"))}`,
                                `citation-fixer ${recordText(citationWorkerPoll, "status") || "-"} / ${shortValue(recordNumber(citationWorkerPoll, "checked"))}`,
                                `contradiction ${recordText(contradictionWorkerProbe, "status") || "-"}${recordText(contradictionWorkerProbe, "ran") ? ` / ran=${recordText(contradictionWorkerProbe, "ran")}` : ""}`,
                              ].join(" · ")}
                            </p>
                          </div>

                          <div className="admin-maintenance-form admin-maintenance-form-contradiction">
                            <label className="admin-maintenance-toggle">
                              <input
                                checked={gbrainContradictionDraft.enabled}
                                onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, enabled: event.target.checked }))}
                                type="checkbox"
                              />
                              冲突探针
                            </label>
                            <input
                              inputMode="numeric"
                              placeholder="间隔小时"
                              value={gbrainContradictionDraft.intervalHours}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, intervalHours: event.target.value }))}
                            />
                            <input
                              placeholder="source id"
                              value={gbrainContradictionDraft.sourceId}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, sourceId: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="topK"
                              value={gbrainContradictionDraft.topK}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, topK: event.target.value }))}
                            />
                            <input
                              inputMode="decimal"
                              placeholder="预算"
                              value={gbrainContradictionDraft.budgetUsd}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, budgetUsd: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="timeout"
                              value={gbrainContradictionDraft.timeoutSeconds}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, timeoutSeconds: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="结果数"
                              value={gbrainContradictionDraft.resultLimit}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, resultLimit: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSaveGBrainContradictionProbe()} type="button">
                              保存探针
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRunGBrainContradictionProbe()} type="button">
                              立即运行
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleTickGBrainContradictionProbe()} type="button">
                              检查到期
                            </button>
                            <textarea
                              placeholder="每行一个 probe 查询"
                              style={{ gridColumn: "1 / -1" }}
                              value={gbrainContradictionDraft.queries}
                              onChange={(event) => setGBrainContradictionDraft((prev) => ({ ...prev, queries: event.target.value }))}
                            />
                          </div>

                          <div className="admin-list" style={{ marginBottom: 12 }}>
                            <div className="admin-row">
                              <div>
                                <strong>Contradiction Probe</strong>
                                <span>
                                  {`状态 ${contradictionProbe?.enabled ? "启用" : "停用"} · 上次 ${formatOptionalDate(contradictionProbe?.last_run_at)} · 下次 ${formatOptionalDate(contradictionProbe?.next_run_at)} · 查询 ${contradictionProbe?.queries?.length ?? 0} · 疑似冲突 ${shortValue(recordNumber(contradictionSummary, "total_contradictions_flagged"))} · Worker ${recordText(contradictionWorkerProbe, "status") || "-"}`}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="admin-maintenance-form admin-maintenance-form-graph">
                            <input
                              placeholder="source id"
                              value={gbrainGraphDraft.sourceId}
                              onChange={(event) => setGBrainGraphDraft((prev) => ({ ...prev, sourceId: event.target.value }))}
                            />
                            <input
                              placeholder="关注实体，如 5Points"
                              value={gbrainGraphDraft.focus}
                              onChange={(event) => setGBrainGraphDraft((prev) => ({ ...prev, focus: event.target.value }))}
                            />
                            <input
                              placeholder="实体类型，可空"
                              value={gbrainGraphDraft.entityType}
                              onChange={(event) => setGBrainGraphDraft((prev) => ({ ...prev, entityType: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleLoadGBrainGraph()} type="button">
                              加载图谱
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleLoadGBrainEntityMergeCandidates()} type="button">
                              实体候选
                            </button>
                          </div>

                          {gbrainGraph ? (
                            <>
                              <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                                <div>
                                  <strong>{gbrainGraph.source_id}</strong>
                                  <span>source</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.focus || "-"}</strong>
                                  <span>关注实体</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.stats?.nodes ?? gbrainGraph.nodes.length}</strong>
                                  <span>节点</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.stats?.edges ?? gbrainGraph.edges.length}</strong>
                                  <span>关系</span>
                                </div>
                                <div>
                                  <strong>{gbrainGraph.stats?.events ?? gbrainGraph.events.length}</strong>
                                  <span>事件</span>
                                </div>
                              </div>

                              <div className="admin-table" style={{ marginBottom: 12 }}>
                                <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1.2fr) 120px minmax(0, 1.4fr)" }}>
                                  <span>实体</span>
                                  <span>类型</span>
                                  <span>引用</span>
                                </div>
                                {graphNodes.map((node) => (
                                  <div className="admin-table-row" key={node.id} style={{ gridTemplateColumns: "minmax(0, 1.2fr) 120px minmax(0, 1.4fr)" }}>
                                    <div className="admin-table-cell" title={node.id}>{node.title}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary">{node.entity_type}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary" title={node.source_file || node.file}>{node.source_file || node.file}</div>
                                  </div>
                                ))}
                                {graphNodes.length === 0 ? (
                                  <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无图谱实体</div>
                                ) : null}
                              </div>

                              <div className="admin-table" style={{ marginBottom: 12 }}>
                                <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1fr) 120px minmax(0, 1fr) minmax(0, 1.2fr)" }}>
                                  <span>起点</span>
                                  <span>关系</span>
                                  <span>终点</span>
                                  <span>证据</span>
                                </div>
                                {graphEdges.map((edge) => (
                                  <div className="admin-table-row" key={edge.id} style={{ gridTemplateColumns: "minmax(0, 1fr) 120px minmax(0, 1fr) minmax(0, 1.2fr)" }}>
                                    <div className="admin-table-cell" title={edge.from}>{graphNodeTitleById.get(edge.from) || edge.from}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary">{edge.relation_type}</div>
                                    <div className="admin-table-cell" title={edge.to}>{graphNodeTitleById.get(edge.to) || edge.to}</div>
                                    <div className="admin-table-cell admin-table-cell-secondary" title={edge.evidence || ""}>{edge.evidence || "-"}</div>
                                  </div>
                                ))}
                                {graphEdges.length === 0 ? (
                                  <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无图谱关系</div>
                                ) : null}
                              </div>

                              <div className="admin-list" style={{ marginBottom: 12 }}>
                                {graphEvents.map((event) => (
                                  <div className="admin-row" key={event.id}>
                                    <div>
                                      <strong>{event.title}</strong>
                                      <span>{[event.date, graphNodeTitleById.get(event.entity_id) || event.entity_id, event.source_file].filter(Boolean).join(" · ")}</span>
                                    </div>
                                  </div>
                                ))}
                                {graphEvents.length === 0 ? (
                                  <div className="admin-row">
                                    <div>
                                      <strong>暂无事件</strong>
                                      <span>{gbrainGraph.warnings?.[0] || "当前过滤条件下没有 source event。"}</span>
                                    </div>
                                  </div>
                                ) : null}
                              </div>
                            </>
                          ) : null}

                          {gbrainEntityMerge ? (
                            <>
                              <div className="admin-metric-grid" style={{ marginBottom: 12 }}>
                                <div>
                                  <strong>{gbrainEntityMerge.source_id}</strong>
                                  <span>候选 source</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.focus || "-"}</strong>
                                  <span>筛选实体</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.stats?.candidates ?? gbrainEntityMerge.candidates.length}</strong>
                                  <span>候选</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.stats?.unresolved ?? "-"}</strong>
                                  <span>未解析</span>
                                </div>
                                <div>
                                  <strong>{gbrainEntityMerge.stats?.duplicates ?? "-"}</strong>
                                  <span>重复页面</span>
                                </div>
                              </div>

                              <div className="admin-table" style={{ marginBottom: 12 }}>
                                <div className="admin-table-header" style={{ gridTemplateColumns: "minmax(0, 1fr) 130px 130px minmax(0, 1.2fr) 132px" }}>
                                  <span>候选实体</span>
                                  <span>类型</span>
                                  <span>建议动作</span>
                                  <span>证据 / 目标</span>
                                  <span style={{ textAlign: "right" }}>操作</span>
                                </div>
                                {entityMergeCandidates.map((candidate) => {
                                  const targets = (candidate.target_nodes ?? []).map((node) => node.title).filter(Boolean).join(", ");
                                  const evidence = (candidate.evidence_edges ?? []).map((edge) => edge.evidence).filter(Boolean).join(", ");
                                  const canCreate = candidate.suggested_action === "create_entity_page" || candidate.suggested_action === "create_event_page";
                                  const canRecordAlias = candidate.suggested_action === "merge_duplicate_pages" || candidate.suggested_action === "link_to_existing_entity";
                                  return (
                                    <div className="admin-table-row" key={candidate.id} style={{ gridTemplateColumns: "minmax(0, 1fr) 130px 130px minmax(0, 1.2fr) 180px" }}>
                                      <div className="admin-table-cell" title={candidate.id}>{candidate.title}</div>
                                      <div className="admin-table-cell admin-table-cell-secondary">{candidate.candidate_type}</div>
                                      <div className="admin-table-cell admin-table-cell-secondary">{candidate.suggested_action}</div>
                                      <div className="admin-table-cell admin-table-cell-secondary" title={candidate.reason || ""}>
                                        {targets || evidence || candidate.reason || "-"}
                                      </div>
                                      <div className="admin-table-cell-actions">
                                        <button className="ghost-button" disabled={adminLoading || !canCreate} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "create_entity_page")} type="button">
                                          创建
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading || !canRecordAlias} onClick={() => void handlePreviewGBrainEntityMergeCandidate(candidate)} type="button">
                                          预览
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading || !canRecordAlias} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "record_alias")} type="button">
                                          别名
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading || !canRecordAlias} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "apply_relink_changes")} type="button">
                                          改写
                                        </button>
                                        <button className="ghost-button" disabled={adminLoading} onClick={() => void handleApplyGBrainEntityMergeCandidate(candidate, "dismiss")} type="button">
                                          忽略
                                        </button>
                                      </div>
                                    </div>
                                  );
                                })}
                                {entityMergeCandidates.length === 0 ? (
                                  <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无实体合并候选</div>
                                ) : null}
                              </div>
                              {gbrainEntityMergePreview ? (
                                <div className="admin-maintenance-card">
                                  <div>
                                    <strong>实体合并预览</strong>
                                    <span>{gbrainEntityMergePreview.planned_alias_review_file || "未生成 alias 文件路径"}</span>
                                  </div>
                                  <p>
                                    主实体：{gbrainEntityMergePreview.canonical_entity?.title || "-"} · 别名：{(gbrainEntityMergePreview.alias_entities ?? []).map((node) => node.title).join(", ") || "-"}
                                  </p>
                                  {(gbrainEntityMergePreview.planned_relink_changes ?? []).slice(0, 6).map((change) => (
                                    <p key={`${change.page_id}-${change.field}-${change.index}`}>
                                      {change.page_title}: {change.diff_preview}
                                    </p>
                                  ))}
                                  {(gbrainEntityMergePreview.planned_relink_changes ?? []).length === 0 ? <p>未发现需要自动改写的 frontmatter 引用。</p> : null}
                                </div>
                              ) : null}
                            </>
                          ) : null}

                          <div className="admin-maintenance-form admin-maintenance-form-citation">
                            <input
                              placeholder="页面 slug"
                              value={citationFixerDraft.pageSlug}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, pageSlug: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="审核 ID"
                              value={citationFixerDraft.reviewId}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, reviewId: event.target.value }))}
                            />
                            <input
                              placeholder="slug 前缀，逗号分隔"
                              value={citationFixerDraft.slugPrefixes}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, slugPrefixes: event.target.value }))}
                            />
                            <input
                              inputMode="numeric"
                              placeholder="turns"
                              value={citationFixerDraft.maxTurns}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, maxTurns: event.target.value }))}
                            />
                            <textarea
                              placeholder="备注"
                              value={citationFixerDraft.notes}
                              onChange={(event) => setCitationFixerDraft((prev) => ({ ...prev, notes: event.target.value }))}
                            />
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handleSubmitCitationFixer()} type="button">
                              提交 citation-fixer
                            </button>
                            <button className="ghost-button" disabled={adminLoading} onClick={() => void handlePollGBrainCitationFixerJobs()} type="button">
                              轮询引用修复
                            </button>
                          </div>

                          <div className="admin-list" style={{ marginBottom: 12 }}>
                            <div className="admin-row">
                              <div>
                                <strong>citation-fixer tracking</strong>
                                <span>
                                  {`跟踪任务 ${citationFixerJobs.length} · 最近轮询 ${formatOptionalDate(gbrainMaintenance?.citation_fixer_jobs?.last_job_poll_at)} · Worker 最近检查 ${shortValue(recordNumber(citationWorkerPoll, "checked"))} 个`}
                                </span>
                              </div>
                            </div>
                            {citationFixerRecentJobs.map((job) => {
                              const reconcile = asRecord(job.reconcile);
                              const git = asRecord(reconcile?.git);
                              const rollback = asRecord(job.rollback);
                              const canRollback = job.status === "completed" && Boolean(git?.commit_hash) && !rollback?.ok;
                              return (
                                <div className="admin-row" key={job.job_id}>
                                  <div>
                                    <strong>{`#${job.job_id} · ${statusLabel(job.status)}`}</strong>
                                    <span>
                                      {[
                                        job.page_slug || "-",
                                        job.source_id || "company-wiki",
                                        job.last_checked_at ? formatDate(job.last_checked_at) : "未轮询",
                                        rollback?.ok ? "已回滚" : null,
                                      ]
                                        .filter(Boolean)
                                        .join(" · ")}
                                    </span>
                                  </div>
                                  {canRollback ? (
                                    <button className="ghost-button" disabled={adminLoading} onClick={() => void handleRollbackGBrainCitationFixerJob(job.job_id)} type="button">
                                      回滚
                                    </button>
                                  ) : null}
                                </div>
                              );
                            })}
                            {citationFixerJobs.length === 0 ? (
                              <div className="admin-row">
                                <div>
                                  <strong>暂无 citation-fixer 追踪任务</strong>
                                  <span>提交引用修复任务后会在这里显示 job 状态。</span>
                                </div>
                              </div>
                            ) : null}
                          </div>

                          <div className="admin-table" style={{ marginBottom: 12 }}>
                            <div className="admin-table-header" style={{ gridTemplateColumns: "70px minmax(0, 1fr) 96px minmax(0, 1.4fr) 140px" }}>
                              <span>ID</span>
                              <span>任务</span>
                              <span>状态</span>
                              <span>进度 / 错误</span>
                              <span style={{ textAlign: "right" }}>操作</span>
                            </div>
                            {jobs.map((job, index) => {
                              const jobId = recordNumber(job, "id");
                              const progress = shortValue(job.progress ?? job.error ?? job.result);
                              return (
                                <div className="admin-table-row" key={`${jobId ?? "job"}-${index}`} style={{ gridTemplateColumns: "70px minmax(0, 1fr) 96px minmax(0, 1.4fr) 140px" }}>
                                  <div className="admin-table-cell">#{jobId ?? "-"}</div>
                                  <div className="admin-table-cell">{recordText(job, "name") || "-"}</div>
                                  <div className="admin-table-cell">{statusLabel(recordText(job, "status"))}</div>
                                  <div className="admin-table-cell admin-table-cell-secondary" title={progress}>{progress}</div>
                                  <div className="admin-table-cell-actions">
                                    <button className="ghost-button" disabled={!jobId || adminLoading} onClick={() => jobId && void handleCancelGBrainJob(jobId)} type="button">取消</button>
                                    <button className="ghost-button" disabled={!jobId || adminLoading} onClick={() => jobId && void handleRetryGBrainJob(jobId)} type="button">重试</button>
                                  </div>
                                </div>
                              );
                            })}
                            {jobs.length === 0 ? (
                              <div className="admin-table-row" style={{ justifyContent: "center", color: "hsl(var(--muted-foreground))" }}>暂无 GBrain 维护任务</div>
                            ) : null}
                          </div>

                          <div className="admin-list">
                            {contradictions.map((item, index) => (
                              <div className="admin-row" key={`${recordText(item, "severity")}-${index}`}>
                                <div>
                                  <strong>{recordText(item, "severity") || "contradiction"}</strong>
                                  <span>{recordText(item, "slug") || recordText(item, "left") || shortValue(item)}</span>
                                </div>
                              </div>
                            ))}
                            {contradictions.length === 0 ? (
                              <div className="admin-row">
                                <div>
                                  <strong>暂无冲突记录</strong>
                                  <span>{gbrainMaintenance?.contradictions?.status === "ok" ? "GBrain 当前没有可展示的 contradiction probe 结果。" : shortValue(gbrainMaintenance?.contradictions?.error)}</span>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        </>
                      );
                    })()}
                  </div>
  );
}
