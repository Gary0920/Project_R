import type { Dispatch, KeyboardEvent, SetStateAction } from "react";

export type WorkspaceMeetingFolderForm = {
  open: boolean;
  topic: string;
  meetingTime: string;
  meetingType: string;
  busy: boolean;
};

const MEETING_TYPE_OPTIONS = [
  "项目统筹会",
  "客户沟通会",
  "技术交底",
  "现场协调",
  "内部复盘",
  "培训分享",
  "其他",
];

type WorkspaceMeetingFolderDialogProps = {
  form: WorkspaceMeetingFolderForm;
  setForm: Dispatch<SetStateAction<WorkspaceMeetingFolderForm>>;
  onSubmit: () => void;
};

export function WorkspaceMeetingFolderDialog({
  form,
  setForm,
  onSubmit,
}: WorkspaceMeetingFolderDialogProps) {
  function close() {
    setForm((prev) => ({ ...prev, open: false }));
  }

  function closeOnEscape(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") close();
  }

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
          <strong>新建会议文件夹</strong>
          <button disabled={form.busy} onClick={close} type="button">×</button>
        </header>
        <label>
          <span>会议主题</span>
          <input
            autoFocus
            disabled={form.busy}
            onChange={(event) => setForm((prev) => ({ ...prev, topic: event.target.value }))}
            onKeyDown={closeOnEscape}
            placeholder="例如：项目启动会"
            value={form.topic}
          />
        </label>
        <label>
          <span>会议时间（可选）</span>
          <input
            disabled={form.busy}
            onChange={(event) => setForm((prev) => ({ ...prev, meetingTime: event.target.value }))}
            onKeyDown={closeOnEscape}
            placeholder="ISO-8601，例如 2026-06-15T09:30"
            value={form.meetingTime}
          />
        </label>
        <label>
          <span>会议类型</span>
          <select
            className="workspace-meeting-type-select"
            disabled={form.busy}
            onChange={(event) => setForm((prev) => ({ ...prev, meetingType: event.target.value }))}
            value={form.meetingType}
          >
            {MEETING_TYPE_OPTIONS.map((meetingType) => (
              <option key={meetingType} value={meetingType}>{meetingType}</option>
            ))}
          </select>
        </label>
        <div>
          <button disabled={form.busy} onClick={close} type="button">取消</button>
          <button disabled={form.busy || !form.topic.trim()} type="submit">创建</button>
        </div>
      </form>
    </div>
  );
}
