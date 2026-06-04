import { type DragEvent, type MouseEvent } from "react";

import type { ChatSessionResponse } from "../../api/types";
import { ChatIcon, AgentIcon, EditIcon, PaperclipIcon, PinIcon, SplitIcon, TrashIcon, WorkspaceIcon } from "../LineIcons";
import { ChatComposer } from "./ChatComposer";
import { ChatMessageList } from "./ChatMessageList";

type SplitPaneKey = "left" | "right";

export type ChatConversationPaneProps = {
  controller: Record<string, any> & {
    pane: SplitPaneKey;
    sessions: ChatSessionResponse[];
  };
};

export function ChatConversationPane({ controller }: ChatConversationPaneProps) {
  const {
    activateConversationPane,
    activeSessionId,
    activeSplitPane,
    activeWorkspace,
    attachmentDragTargetPane,
    commitRename,
    currentUser,
    handleAttachmentDragEnter,
    handleAttachmentDragLeave,
    handleAttachmentDragOver,
    handleAttachmentDrop,
    handlePinSession,
    handleRenameSession,
    handleToggleSideBySide,
    messagesBySession,
    mode,
    pane,
    renameInput,
    sessions,
    sendingSessions,
    setDeleteConfirmSessionId,
    setRenameInput,
    setUtilityPanel,
    sideBySideOpen,
    splitPaneSessionIds,
    titleInputRef,
    utilityPanel,
    formatSessionDisplayTitle,
  } = controller;

    const paneSessionId = sideBySideOpen ? splitPaneSessionIds[pane] : activeSessionId;
    const paneSession = paneSessionId ? sessions.find((session) => session.id === paneSessionId) ?? null : null;
    const paneMessages = paneSessionId ? messagesBySession[paneSessionId] ?? [] : [];
    const isActivePane = !sideBySideOpen || activeSplitPane === pane;
    const isEmptySplitPane = sideBySideOpen && !paneSessionId;
    const isAttachmentDragOver = attachmentDragTargetPane === pane;

    return (
      <div
        className={`chat-conversation-pane ${isActivePane ? "is-active" : ""} ${isAttachmentDragOver ? "is-attachment-drag-over" : ""}`}
        onDragEnter={(event) => handleAttachmentDragEnter(event, pane)}
        onDragLeave={(event) => handleAttachmentDragLeave(event, pane)}
        onDragOver={(event) => handleAttachmentDragOver(event, pane)}
        onDrop={(event) => handleAttachmentDrop(event, pane, paneSessionId)}
        onClick={() => activateConversationPane(pane, paneSessionId)}
        key={pane}
      >
        {isAttachmentDragOver ? (
          <div className="attachment-drop-overlay">
            <div>
              <PaperclipIcon />
              <strong>释放以添加到当前对话</strong>
              <span>图片随本条消息发送，文本和 PDF 作为会话临时附件处理。</span>
            </div>
          </div>
        ) : null}
        <header className="chat-header">
          <div className="chat-header-title">
            <span className="chat-header-mode-icon">{mode === "agent" ? <AgentIcon /> : <ChatIcon />}</span>
            {paneSession && renameInput?.id === paneSession.id && renameInput.scope === "header" ? (
              <input
                autoFocus
                className="chat-title-input"
                onBlur={() => void commitRename()}
                onChange={(event) => setRenameInput({ id: paneSession.id, value: event.target.value, scope: "header" })}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void commitRename();
                  if (event.key === "Escape") setRenameInput(null);
                }}
                onClick={(event) => event.stopPropagation()}
                onMouseDown={(event) => event.stopPropagation()}
                ref={titleInputRef}
                value={renameInput.value}
              />
            ) : (
              <button
                className="chat-title-button"
                disabled={!paneSession}
                onMouseDown={(event) => {
                  if (!paneSession) return;
                  event.preventDefault();
                  event.stopPropagation();
                  handleRenameSession(paneSession.id, "header");
                }}
                onKeyDown={(event) => {
                  if (!paneSession) return;
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    handleRenameSession(paneSession.id, "header");
                  }
                }}
                type="button"
              >
                <h1>{paneSession ? formatSessionDisplayTitle(paneSession.title) : (sideBySideOpen ? `${pane === "left" ? "左侧" : "右侧"}对话` : "新会话")}</h1>
                {paneSession ? <EditIcon /> : null}
              </button>
            )}
            {sideBySideOpen ? <span className="chat-workspace-chip">{isActivePane ? "当前输入区" : "点击激活"}</span> : null}
            {activeWorkspace && !sideBySideOpen ? <span className="chat-workspace-chip">{activeWorkspace.name}</span> : null}
          </div>
          <div className="chat-header-actions">
            <button
              className={`icon-button ${paneSession?.is_pinned ? "is-active" : ""}`}
              disabled={!paneSession}
              onClick={() => paneSession ? void handlePinSession(paneSession.id) : undefined}
              title={paneSession?.is_pinned ? "取消置顶" : "置顶"}
              type="button"
            >
              <PinIcon />
            </button>
            <button
              aria-pressed={sideBySideOpen}
              className={`icon-button ${sideBySideOpen ? "is-active" : ""}`}
              onClick={handleToggleSideBySide}
              title={sideBySideOpen ? "关闭对话并排" : "左右并排两个对话"}
              type="button"
            >
              <SplitIcon />
            </button>
            {activeWorkspace?.workspace_kind !== "user" ? (
              <button
                className={`icon-button ${utilityPanel === "workspace" ? "is-active" : ""}`}
                onClick={() => setUtilityPanel((value: string | null) => value === "workspace" ? null : "workspace")}
                title={utilityPanel === "workspace" ? "关闭工作区资料" : "工作区资料"}
                type="button"
              >
                <WorkspaceIcon />
              </button>
            ) : null}
            {paneSession ? (
              <button className="icon-button" onClick={() => setDeleteConfirmSessionId(paneSession.id)} title="删除当前会话" type="button">
                <TrashIcon />
              </button>
            ) : null}
          </div>
        </header>

        <ChatMessageList
          controller={{
            ...controller,
            isActivePane,
            isEmptySplitPane,
            messages: paneMessages,
            paneSessionId,
            sessionIsSending: paneSessionId ? Boolean(sendingSessions[paneSessionId]) : false,
          } as any}
        />

        <ChatComposer
          controller={{
            ...controller,
            isActivePane,
            paneSessionId,
          } as any}
        />
      </div>
    );
}
