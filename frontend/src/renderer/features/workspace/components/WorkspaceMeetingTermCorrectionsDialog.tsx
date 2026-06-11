import type { Dispatch, SetStateAction } from "react";

export type WorkspaceMeetingTermCorrection = {
  original: string;
  corrected: string;
};

type WorkspaceMeetingTermCorrectionsDialogProps = {
  corrections: WorkspaceMeetingTermCorrection[];
  setCorrections: Dispatch<SetStateAction<WorkspaceMeetingTermCorrection[]>>;
  busy: boolean;
  editOriginal: string;
  editCorrected: string;
  setEditOriginal: Dispatch<SetStateAction<string>>;
  setEditCorrected: Dispatch<SetStateAction<string>>;
  onClose: () => void;
  onSave: () => void;
};

export function WorkspaceMeetingTermCorrectionsDialog({
  corrections,
  setCorrections,
  busy,
  editOriginal,
  editCorrected,
  setEditOriginal,
  setEditCorrected,
  onClose,
  onSave,
}: WorkspaceMeetingTermCorrectionsDialogProps) {
  function addCorrection() {
    setCorrections((prev) => [...prev, { original: editOriginal.trim(), corrected: editCorrected.trim() }]);
    setEditOriginal("");
    setEditCorrected("");
  }

  return (
    <div className="workspace-text-prompt-overlay" onClick={() => !busy && onClose()}>
      <div
        className="workspace-text-prompt"
        onClick={(event) => event.stopPropagation()}
        style={{ maxWidth: 500 }}
      >
        <header>
          <strong>术语纠错</strong>
          <button disabled={busy} onClick={onClose} type="button">×</button>
        </header>
        <div style={{ background: "var(--warning)/0.1", padding: "8px 12px", borderRadius: 6, marginBottom: 10, fontSize: "0.9em", lineHeight: 1.5 }}>
          <strong>转录中这些词是否需要修正？</strong>
          <p style={{ margin: "4px 0 0", opacity: 0.75 }}>
            音视频转录可能将专业术语、人名、地名词识别错误。请检查并修正：添加原识别词和正确写法，例如 "波离" → "玻璃"、"五矿" → "5mm"。
            已保存的术语会在下次生成纪要时自动应用。跳过将保留原始识别结果，未确认术语在纪要中标记为「待确认」。
          </p>
        </div>
        {corrections.length > 0 ? (
          <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 12 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>原识别</th>
                <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid #ccc" }}>建议修正</th>
                <th style={{ width: 60, borderBottom: "1px solid #ccc" }} />
              </tr>
            </thead>
            <tbody>
              {corrections.map((correction, index) => (
                <tr key={index}>
                  <td style={{ padding: "4px 8px" }}>{correction.original}</td>
                  <td style={{ padding: "4px 8px" }}>{correction.corrected}</td>
                  <td style={{ padding: "4px 8px" }}>
                    <button
                      disabled={busy}
                      onClick={() => setCorrections((prev) => prev.filter((_, itemIndex) => itemIndex !== index))}
                      type="button"
                      style={{ background: "none", border: "none", color: "#d00", cursor: "pointer" }}
                    >×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <input
            disabled={busy}
            onChange={(event) => setEditOriginal(event.target.value)}
            placeholder="原识别"
            style={{ flex: 1 }}
            value={editOriginal}
          />
          <input
            disabled={busy}
            onChange={(event) => setEditCorrected(event.target.value)}
            placeholder="建议修正"
            style={{ flex: 1 }}
            value={editCorrected}
          />
          <button
            disabled={busy || !editOriginal.trim() || !editCorrected.trim()}
            onClick={addCorrection}
            type="button"
          >添加</button>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button disabled={busy} onClick={onClose} type="button">跳过</button>
          <button disabled={busy || corrections.length === 0} onClick={onSave} type="button">保存</button>
        </div>
      </div>
    </div>
  );
}
