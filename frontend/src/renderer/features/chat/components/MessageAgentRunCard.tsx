import type { AgentRunResponse } from "../../../shared/api/types";
import { AgentIcon } from "../../../shared/icons/LineIcons";
import { missingInputInstruction } from "../messageInstructions";
import { MessageExecutionSummary, sanitizeAgentSummaryTitle } from "./MessageExecutionSummary";

function agentRunStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待输入";
  if (status === "queued") return "排队中";
  if (status === "cancelled") return "已取消";
  return "执行中";
}

function agentEventStatusLabel(status: string) {
  if (status === "completed") return "完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待";
  if (status === "queued") return "排队";
  return "进行中";
}

function agentEventDetail(event: AgentRunResponse["events"][number] | undefined) {
  if (!event) return "";
  const missingInputs = Array.isArray(event.payload?.missing_inputs)
    ? event.payload.missing_inputs as Array<Record<string, unknown>>
    : [];
  if (missingInputs.length) {
    const instruction = missingInputInstruction(null, missingInputs);
    if (instruction) return instruction;
  }
  return event.detail;
}

function AgentRunAudit({ agentRun }: { agentRun: AgentRunResponse }) {
  const events = agentRun.events ?? [];
  const completedEvents = events.filter((event) => event.status === "completed").length;
  const isPlanning = ["queued", "waiting"].includes(agentRun.status);
  const activeEvent = events.find((event) => event.status === "running" || event.status === "waiting")
    ?? events.find((event) => event.status === "queued")
    ?? events[events.length - 1];
  const failedEvent = events.find((event) => event.status === "failed");
  const progressPercent = events.length
    ? Math.round((completedEvents / events.length) * 100)
    : (agentRun.status === "completed" ? 100 : 0);
  const planSummary = events.length
    ? events.slice(0, 4).map((event) => event.title).join(" / ")
    : "等待后端返回执行步骤。";

  return (
    <div className="message-agent-audit">
      {events.length ? (
        <div className="message-agent-progress" aria-label={`执行进度 ${progressPercent}%`}>
          <span style={{ width: `${progressPercent}%` }} />
        </div>
      ) : null}
      <div className="message-agent-plan-grid">
        <section>
          <span>任务理解</span>
          <p>{agentRun.title || "Agent 正在理解本次任务目标。"}</p>
        </section>
        <section>
          <span>执行计划</span>
          <p>{planSummary}</p>
        </section>
      </div>
      {activeEvent || failedEvent ? (
        <div className={`message-agent-current-step ${failedEvent ? "is-failed" : ""}`}>
          <span>{failedEvent ? "失败位置" : "当前步骤"}</span>
          <strong>{(failedEvent ?? activeEvent)?.title}</strong>
          {agentEventDetail(failedEvent ?? activeEvent) ? <p>{agentEventDetail(failedEvent ?? activeEvent)}</p> : null}
        </div>
      ) : null}
      {isPlanning ? (
        <div className="message-agent-plan-actions">
          <button disabled type="button">确认执行</button>
          <button disabled type="button">修改计划</button>
          <small>当前后端尚未接入计划审批；此处只展示计划形态。</small>
        </div>
      ) : null}
      {events.length ? (
        <ol className="message-agent-event-list">
          {events.map((event) => (
            <li className={`message-agent-event is-${event.status}`} key={event.id}>
              <span className="message-agent-event-dot" />
              <div>
                <div className="message-agent-event-title">
                  <strong>{event.title}</strong>
                  <small>{agentEventStatusLabel(event.status)}</small>
                </div>
                {agentEventDetail(event) ? <p>{agentEventDetail(event)}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      {agentRun.error_message ? <p className="message-agent-run-error">{agentRun.error_message}</p> : null}
    </div>
  );
}

export function MessageAgentRunCard({ agentRun }: { agentRun: AgentRunResponse }) {
  const events = agentRun.events ?? [];
  const isFinished = agentRun.status === "completed" || agentRun.status === "failed";
  const isPlanning = ["queued", "waiting"].includes(agentRun.status);
  const completedEvents = events.filter((event) => event.status === "completed").length;

  if (isFinished) {
    return (
      <MessageExecutionSummary
        defaultExpanded={agentRun.status === "failed"}
        kind="agent"
        status={agentRun.status}
        stepCount={events.length}
        title={sanitizeAgentSummaryTitle(agentRun.title || "Agent 任务")}
      >
        <AgentRunAudit agentRun={agentRun} />
      </MessageExecutionSummary>
    );
  }

  return (
    <div className={`message-agent-run-card is-${agentRun.status}`}>
      <div className="message-agent-run-header">
        <span className="message-agent-run-icon"><AgentIcon /></span>
        <div>
          <strong>{agentRun.title}</strong>
          <span>
            {isPlanning ? "计划模式" : agentRunStatusLabel(agentRun.status)}
            {events.length ? ` · 步骤 ${completedEvents}/${events.length}` : ""}
          </span>
        </div>
      </div>
      <AgentRunAudit agentRun={agentRun} />
    </div>
  );
}
