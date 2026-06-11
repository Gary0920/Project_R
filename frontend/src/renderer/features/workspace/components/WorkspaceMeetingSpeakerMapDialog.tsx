import type { Dispatch, SetStateAction } from "react";

import type { DetectedSpeaker } from "../../../shared/api/types";

type WorkspaceMeetingSpeakerMapDialogProps = {
  loading: boolean;
  speakers: DetectedSpeaker[];
  speakerNames: Record<string, string>;
  setSpeakerNames: Dispatch<SetStateAction<Record<string, string>>>;
  onClose: () => void;
  onSave: () => void;
};

export function WorkspaceMeetingSpeakerMapDialog({
  loading,
  speakers,
  speakerNames,
  setSpeakerNames,
  onClose,
  onSave,
}: WorkspaceMeetingSpeakerMapDialogProps) {
  return (
    <div className="workspace-text-prompt-overlay" onClick={() => !loading && onClose()}>
      <div
        className="workspace-text-prompt"
        onClick={(event) => event.stopPropagation()}
        style={{ maxWidth: 500 }}
      >
        <header>
          <strong>说话人映射</strong>
          <button disabled={loading} onClick={onClose} type="button">×</button>
        </header>
        <div style={{ background: "var(--warning)/0.1", padding: "8px 12px", borderRadius: 6, marginBottom: 10, fontSize: "0.9em", lineHeight: 1.5 }}>
          <strong>需要标记发言人吗？</strong>
          <p style={{ margin: "4px 0 0", opacity: 0.75 }}>
            系统已自动检测到以下说话人。为每个人填写真实姓名，生成纪要时就会使用姓名而非 "Speaker 1"。
            跳过将保留为「待确认」，可以在后续随时补充。
          </p>
        </div>
        {loading ? (
          <p>正在读取说话人信息...</p>
        ) : speakers.length === 0 ? (
          <p>未检测到说话人。可以跳过此步骤，未确认项将被标记为「待确认」。</p>
        ) : (
          <div>
            <p style={{ opacity: 0.7, marginBottom: 8, fontSize: "0.85em" }}>点击说话人ID下方的输入框，填写显示名称。</p>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>说话人ID</th>
                  <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>显示名称</th>
                  <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>发言占比</th>
                </tr>
              </thead>
              <tbody>
                {speakers.map((speaker) => (
                  <tr key={speaker.speaker_id}>
                    <td style={{ padding: "4px 8px" }}>{speaker.speaker_id}</td>
                    <td style={{ padding: "4px 8px" }}>
                      <input
                        style={{ width: "100%", boxSizing: "border-box" }}
                        value={speakerNames[speaker.speaker_id] ?? speaker.display_name}
                        onChange={(event) => setSpeakerNames((prev) => ({ ...prev, [speaker.speaker_id]: event.target.value }))}
                      />
                    </td>
                    <td style={{ padding: "4px 8px" }}>{speaker.ratio}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ marginTop: 12, display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button disabled={loading} onClick={onClose} type="button">跳过</button>
          <button disabled={loading || speakers.length === 0} onClick={onSave} type="button">保存映射</button>
        </div>
      </div>
    </div>
  );
}
