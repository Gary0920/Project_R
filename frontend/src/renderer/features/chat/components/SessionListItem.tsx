import type { KeyboardEvent, MouseEvent, RefObject } from "react";

import { PinIcon } from "../../../shared/icons/LineIcons";

type SessionListItemProps = {
  activeSessionId: number | null;
  commitRename: () => Promise<void> | void;
  formatSessionDisplayTitle: (title: string) => string;
  formatSidebarTime: (value: string) => string;
  openSessionMenu: (event: MouseEvent<HTMLElement>, session: any) => void;
  renameInput: { id: number; value: string; scope: string } | null;
  session: any;
  selectSession: (session: any, openInSplitPane?: boolean) => void;
  setRenameInput: (value: any) => void;
  sideBySideOpen: boolean;
  sidebarRenameInputRef: RefObject<HTMLInputElement | null>;
  splitPaneSessionIds: { left: number | null; right: number | null };
};

export function SessionListItem({
  activeSessionId,
  commitRename,
  formatSessionDisplayTitle,
  formatSidebarTime,
  openSessionMenu,
  renameInput,
  session,
  selectSession,
  setRenameInput,
  sideBySideOpen,
  sidebarRenameInputRef,
  splitPaneSessionIds,
}: SessionListItemProps) {
  const activeRenameInput = renameInput && renameInput.id === session.id && renameInput.scope === "sidebar" ? renameInput : null;

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectSession(session);
    }
  }

  return (
    <div
      className={`session-item ${session.id === activeSessionId ? "is-active" : ""} ${sideBySideOpen && session.id === splitPaneSessionIds.left ? "is-in-left-pane" : ""} ${sideBySideOpen && session.id === splitPaneSessionIds.right ? "is-in-right-pane" : ""}`}
      onClick={(event) => selectSession(session, event.ctrlKey)}
      onAuxClick={(event) => {
        if (event.button === 1) selectSession(session, true);
      }}
      onContextMenu={(event) => openSessionMenu(event, session)}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
    >
      {activeRenameInput ? (
        <input
          autoFocus
          className="session-rename-input"
          onBlur={() => void commitRename()}
          onChange={(event) => setRenameInput({ ...activeRenameInput, value: event.target.value })}
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
          onKeyDown={(event) => {
            if (event.key === "Enter") void commitRename();
            if (event.key === "Escape") setRenameInput(null);
          }}
          ref={sidebarRenameInputRef}
          value={activeRenameInput.value}
        />
      ) : (
        <span className="session-title">
          {session.is_pinned ? <span className="session-pin-badge"><PinIcon />置顶</span> : null}
          <span>{formatSessionDisplayTitle(session.title)}</span>
        </span>
      )}
      <span className="session-time">{formatSidebarTime(session.updated_at)}</span>
    </div>
  );
}
