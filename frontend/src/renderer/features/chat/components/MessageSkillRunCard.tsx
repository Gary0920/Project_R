import type { GeneratedFileResponse, SkillRunResponse, WorkspaceResponse } from "../../../shared/api/types";
import { missingInputInstruction } from "../messageInstructions";
import { MessageCodeBlock } from "./MessageCodeBlock";
import { MessageExecutionSummary } from "./MessageExecutionSummary";
import { MessageGeneratedFile } from "./MessageGeneratedFile";

export type MessageSkillRunCardProps = {
  showGeneratedFile?: boolean;
  skillRun: SkillRunResponse;
  onCopyGeneratedEmailBody?: (file: GeneratedFileResponse) => Promise<void>;
  onEditGeneratedEmailDraft?: (file: GeneratedFileResponse) => void;
  onOpenGeneratedEmailClient?: (file: GeneratedFileResponse) => void;
  onSaveGeneratedFileToWorkspace?: (file: GeneratedFileResponse) => Promise<{ path: string }>;
  serverUrl: string;
  token: string | null;
  workspace?: WorkspaceResponse | null;
};

function skillRunStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "ready") return "待执行";
  if (status === "failed") return "失败";
  if (status === "running") return "执行中";
  return "收集中";
}

function SkillRunAudit({
  dispatchSteps,
  missingFields,
}: {
  dispatchSteps: Array<Record<string, unknown>>;
  missingFields: string[];
}) {
  return (
    <div className="message-skill-audit">
      {dispatchSteps.length ? (
        <div className="message-skill-dispatch">
          {dispatchSteps.map((step, index) => (
            <span key={`${String(step.id ?? index)}-${String(step.tool ?? "")}`}>
              {String(step.label ?? step.tool ?? "执行步骤")}
            </span>
          ))}
        </div>
      ) : null}
      {missingFields.length ? (
        <div className="message-skill-fields">
          {missingFields.map((field) => (
            <span key={field}>{field}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function MessageSkillRunCard({
  showGeneratedFile = true,
  skillRun,
  onCopyGeneratedEmailBody,
  onEditGeneratedEmailDraft,
  onOpenGeneratedEmailClient,
  onSaveGeneratedFileToWorkspace,
  serverUrl,
  token,
  workspace,
}: MessageSkillRunCardProps) {
  const missingFields = skillRun.missing_inputs
    .map((item) => String(item.label ?? item.name ?? "待补充字段"))
    .filter(Boolean);
  const missingInstruction = missingFields.length
    ? missingInputInstruction(skillRun.skill_name, skillRun.missing_inputs)
    : "";
  const dispatchSteps = Array.isArray(skillRun.dispatch?.steps)
    ? skillRun.dispatch.steps as Array<Record<string, unknown>>
    : [];
  const displayName = skillRun.skill?.display_name ?? skillRun.skill_name;
  const isFinished = skillRun.status === "completed" || skillRun.status === "failed";

  if (isFinished) {
    return (
      <>
        {showGeneratedFile && skillRun.generated_file ? (
          <MessageGeneratedFile
            activeWorkspace={workspace}
            file={skillRun.generated_file}
            onCopyEmailBody={onCopyGeneratedEmailBody}
            onEditEmailDraft={onEditGeneratedEmailDraft}
            onOpenEmailClient={onOpenGeneratedEmailClient}
            onSaveToWorkspace={onSaveGeneratedFileToWorkspace}
            serverUrl={serverUrl}
            token={token}
            variant="document"
          />
        ) : skillRun.generated_file ? (
          <div className="message-deliverable-filename">{skillRun.generated_file.filename}</div>
        ) : null}
        <MessageExecutionSummary
          defaultExpanded={skillRun.status === "failed"}
          kind="skill"
          status={skillRun.status}
          stepCount={dispatchSteps.length}
          title={displayName}
        >
          <SkillRunAudit dispatchSteps={dispatchSteps} missingFields={missingFields} />
        </MessageExecutionSummary>
      </>
    );
  }

  return (
    <div className="message-skill-card">
      <div className="message-skill-header">
        <strong>{displayName}</strong>
        <span>{skillRunStatusLabel(skillRun.status)}</span>
      </div>
      {dispatchSteps.length ? (
        <div className="message-skill-dispatch">
          {dispatchSteps.map((step, index) => (
            <span key={`${String(step.id ?? index)}-${String(step.tool ?? "")}`}>
              {String(step.label ?? step.tool ?? "执行步骤")}
            </span>
          ))}
        </div>
      ) : null}
      {missingFields.length ? (
        <div className="message-skill-fields">
          {missingFields.map((field) => (
            <span key={field}>{field}</span>
          ))}
        </div>
      ) : null}
      {missingInstruction ? (
        <MessageCodeBlock code={missingInstruction} language="下一步操作" />
      ) : null}
      {showGeneratedFile && skillRun.generated_file ? (
        <MessageGeneratedFile
          activeWorkspace={workspace}
          file={skillRun.generated_file}
          onCopyEmailBody={onCopyGeneratedEmailBody}
          onEditEmailDraft={onEditGeneratedEmailDraft}
          onOpenEmailClient={onOpenGeneratedEmailClient}
          onSaveToWorkspace={onSaveGeneratedFileToWorkspace}
          serverUrl={serverUrl}
          token={token}
        />
      ) : skillRun.generated_file ? (
        <div className="message-skill-output">{skillRun.generated_file.filename}</div>
      ) : null}
    </div>
  );
}
