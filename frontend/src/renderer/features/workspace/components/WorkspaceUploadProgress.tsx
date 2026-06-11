export type WorkspaceUploadProgressState = {
  active: boolean;
  current: number;
  total: number;
  filename: string;
};

type WorkspaceUploadProgressProps = {
  progress: WorkspaceUploadProgressState;
};

export function WorkspaceUploadProgress({ progress }: WorkspaceUploadProgressProps) {
  if (!progress.active) return null;

  const percent = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;

  return (
    <div className="workspace-upload-progress">
      <div className="workspace-upload-progress-meta">
        <span>正在上传 {progress.filename}</span>
        <strong>{percent}%</strong>
      </div>
      <div className="workspace-upload-progress-track"><span style={{ width: `${percent}%` }} /></div>
    </div>
  );
}
