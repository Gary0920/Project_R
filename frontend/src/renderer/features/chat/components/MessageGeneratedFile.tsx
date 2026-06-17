import type { GeneratedFileResponse, WorkspaceResponse } from "../../../shared/api/types";
import { downloadGeneratedFile } from "../generatedFiles";
import { GeneratedFileCard } from "./GeneratedFileCard";

export type MessageGeneratedFileProps = {
  activeWorkspace?: WorkspaceResponse | null;
  file: GeneratedFileResponse;
  onCopyEmailBody?: (file: GeneratedFileResponse) => Promise<void>;
  onEditEmailDraft?: (file: GeneratedFileResponse) => void;
  onOpenEmailClient?: (file: GeneratedFileResponse) => void;
  onSaveToWorkspace?: (file: GeneratedFileResponse) => Promise<{ path: string }>;
  serverUrl: string;
  token: string | null;
};

export function MessageGeneratedFile({
  activeWorkspace,
  file,
  onCopyEmailBody,
  onEditEmailDraft,
  onOpenEmailClient,
  onSaveToWorkspace,
  serverUrl,
  token,
}: MessageGeneratedFileProps) {
  return (
    <GeneratedFileCard
      file={file}
      onDownload={(generatedFile) => void downloadGeneratedFile(serverUrl, token, generatedFile)}
      onCopyEmailBody={onCopyEmailBody}
      onEditEmailDraft={onEditEmailDraft}
      onOpenEmailClient={onOpenEmailClient}
      onSaveToWorkspace={onSaveToWorkspace}
      workspace={activeWorkspace}
    />
  );
}
