import type { AgentRunResponse } from "../../../shared/api/types";
import { AgentIcon } from "../../../shared/icons/LineIcons";

type WorkspaceAgentRunToastProps = {
  run: AgentRunResponse;
  expanded: boolean;
  leaving: boolean;
  onDismiss: () => void;
  onToggleDetails: () => void;
};

function agentRunStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "waiting") return "等待输入";
  if (status === "queued") return "排队中";
  return "执行中";
}

function compactText(value: string, maxLength = 140) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}...` : normalized;
}

export function WorkspaceAgentRunToast({
  run,
  expanded,
  leaving,
  onDismiss,
  onToggleDetails,
}: WorkspaceAgentRunToastProps) {
  const events = run.events ?? [];
  const failedIndexFromEnd = [...events].reverse().findIndex((event) => event.status === "failed");
  const latestIndex = failedIndexFromEnd >= 0 ? events.length - 1 - failedIndexFromEnd : events.length - 1;
  const latestEvent = latestIndex >= 0 ? events[latestIndex] : undefined;
  const hasDetails = events.length > 0 || Boolean(run.error_message);
  return (
    <div className={`workspace-agent-run-toast is-${run.status} ${leaving ? "is-leaving" : ""}`}>
      <div className="workspace-agent-run-header">
        <span className="workspace-agent-run-icon"><AgentIcon /></span>
        <div>
          <strong>{run.title}</strong>
          <span>{agentRunStatusLabel(run.status)}</span>
        </div>
        <button aria-label="关闭录入状态" onClick={onDismiss} title="关闭" type="button">×</button>
      </div>
      {latestEvent ? (
        <div className={`workspace-agent-run-latest is-${latestEvent.status}`}>
          <span className="workspace-agent-run-dot" />
          <div>
            <strong>{latestEvent.title}</strong>
          </div>
          <small>{latestEvent.status}</small>
        </div>
      ) : null}
      {hasDetails ? (
        <>
          <button className="workspace-agent-run-detail-button" onClick={onToggleDetails} type="button">
            {expanded ? "收起详情" : "查看详情"}
          </button>
          {expanded ? (
            <div className="workspace-agent-run-details">
              {events.length ? (
                <ol>
                  {events.map((event) => (
                    <li className={`workspace-agent-run-history is-${event.status}`} key={event.id}>
                      <span className="workspace-agent-run-dot" />
                      <div>
                        <strong>{event.title}</strong>
                        {event.detail ? <p>{compactText(event.detail, 420)}</p> : null}
                      </div>
                      <small>{event.status}</small>
                    </li>
                  ))}
                </ol>
              ) : null}
              {run.error_message ? (
                <p className="workspace-agent-run-error">
                  {run.error_message}。请检查文件权限、网络或 GBrain 服务状态后重新执行。
                </p>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
