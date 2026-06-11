import type { ChangeEvent, Dispatch, KeyboardEvent, SetStateAction } from "react";

export type WorkspaceMeetingTranscriptForm = {
  open: boolean;
  folderPath: string;
  content: string;
  selectedFile: File | null;
  busy: boolean;
};

type WorkspaceMeetingTranscriptDialogProps = {
  form: WorkspaceMeetingTranscriptForm;
  setForm: Dispatch<SetStateAction<WorkspaceMeetingTranscriptForm>>;
  onFileSelect: (event: ChangeEvent<HTMLInputElement>) => void;
  onSubmit: () => void;
};

export function WorkspaceMeetingTranscriptDialog({
  form,
  setForm,
  onFileSelect,
  onSubmit,
}: WorkspaceMeetingTranscriptDialogProps) {
  function close() {
    setForm((prev) => ({ ...prev, open: false }));
  }

  function closeOnEscape(event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) {
    if (event.key === "Escape") close();
  }

  const selectedFileIsDocx = form.selectedFile !== null && form.selectedFile.name.toLowerCase().endsWith(".docx");

  return (
    <div className="workspace-text-prompt-overlay" onClick={() => !form.busy && close()}>
      <form
        className="workspace-text-prompt"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <header>
          <strong>保存会议转录文本</strong>
          <button disabled={form.busy} onClick={close} type="button">×</button>
        </header>
        <label>
          <span>会议文件夹路径</span>
          <input
            disabled={form.busy}
            onChange={(event) => setForm((prev) => ({ ...prev, folderPath: event.target.value }))}
            onKeyDown={closeOnEscape}
            placeholder="例如：20-会议与沟通/20260615-0930-项目启动会"
            value={form.folderPath}
          />
        </label>
        <label>
          <span>转录来源</span>
          <div className="workspace-transcript-source">
            <label className="workspace-file-upload-button">
              <input
                accept=".txt,.md,.markdown,.docx"
                disabled={form.busy}
                onChange={onFileSelect}
                type="file"
              />
              选择文件 (TXT / MD / DOCX)
            </label>
            {form.selectedFile ? (
              <span className="workspace-transcript-file-name">
                {form.selectedFile.name}
                <button
                  className="workspace-file-action"
                  disabled={form.busy}
                  onClick={() => setForm((prev) => ({ ...prev, selectedFile: null, content: "" }))}
                  type="button"
                  title="清除文件"
                >×</button>
              </span>
            ) : null}
          </div>
        </label>
        <label>
          <span>转录内容{form.selectedFile ? "（预览）" : ""}</span>
          <textarea
            autoFocus
            disabled={form.busy || selectedFileIsDocx}
            onChange={(event) => setForm((prev) => ({ ...prev, content: event.target.value }))}
            onKeyDown={closeOnEscape}
            placeholder={selectedFileIsDocx ? "DOCX 文件将由服务器解析..." : "在此粘贴会议转录文本，或选择文件自动填充..."}
            rows={10}
            value={form.content}
          />
        </label>
        <div>
          <button disabled={form.busy} onClick={close} type="button">取消</button>
          <button
            disabled={
              form.busy
              || !form.folderPath.trim()
              || (!form.content.trim() && !form.selectedFile)
            }
            type="submit"
          >保存</button>
        </div>
      </form>
    </div>
  );
}
