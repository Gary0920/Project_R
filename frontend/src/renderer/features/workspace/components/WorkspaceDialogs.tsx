import type { KeyboardEvent } from "react";

export type WorkspaceConfirmation = {
  title: string;
  detail: string;
  confirmLabel: string;
  tone: "warning" | "danger";
  onConfirm: () => Promise<void>;
};

export type WorkspaceTextPrompt = {
  title: string;
  label: string;
  initialValue: string;
  confirmLabel: string;
  onConfirm: (value: string) => Promise<void>;
};

type WorkspaceConfirmationCardProps = {
  confirmation: WorkspaceConfirmation;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function WorkspaceConfirmationCard({
  confirmation,
  busy,
  onCancel,
  onConfirm,
}: WorkspaceConfirmationCardProps) {
  return (
    <div className={`workspace-confirm-card is-${confirmation.tone}`}>
      <div>
        <strong>{confirmation.title}</strong>
        <span>{confirmation.detail}</span>
      </div>
      <div className="workspace-confirm-actions">
        <button disabled={busy} onClick={onCancel} type="button">取消</button>
        <button disabled={busy} onClick={onConfirm} type="button">{confirmation.confirmLabel}</button>
      </div>
    </div>
  );
}

type WorkspaceTextPromptDialogProps = {
  prompt: WorkspaceTextPrompt;
  value: string;
  busy: boolean;
  onCancel: () => void;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export function WorkspaceTextPromptDialog({
  prompt,
  value,
  busy,
  onCancel,
  onChange,
  onSubmit,
}: WorkspaceTextPromptDialogProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") onCancel();
  }

  return (
    <div className="workspace-text-prompt-overlay" onClick={() => !busy && onCancel()}>
      <form
        className="workspace-text-prompt"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <header>
          <strong>{prompt.title}</strong>
          <button disabled={busy} onClick={onCancel} type="button">×</button>
        </header>
        <label>
          <span>{prompt.label}</span>
          <input
            autoFocus
            disabled={busy}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            value={value}
          />
        </label>
        <div>
          <button disabled={busy} onClick={onCancel} type="button">取消</button>
          <button disabled={busy || !value.trim()} type="submit">{prompt.confirmLabel}</button>
        </div>
      </form>
    </div>
  );
}
