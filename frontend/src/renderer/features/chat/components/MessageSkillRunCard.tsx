import type { GeneratedFileResponse, SkillRunResponse, WorkspaceResponse } from "../../../shared/api/types";
import { missingInputInstruction } from "../messageInstructions";
import { MessageCodeBlock } from "./MessageCodeBlock";
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
  const dispatchSteps = Array.isArray(skillRun.dispatch?.steps) ? skillRun.dispatch.steps as Array<Record<string, unknown>> : [];
  return (
    <div className="message-skill-card">
      <div className="message-skill-header">
        <strong>{skillRun.skill?.display_name ?? skillRun.skill_name}</strong>
        <span>{skillRun.status === "completed" ? "已完成" : skillRun.status === "ready" ? "待执行" : skillRun.status === "failed" ? "失败" : "收集中"}</span>
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
