import { useEffect, useState, type RefObject } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import type {
  GeneratedFileResponse,
  WorkspaceResponse,
} from "../../../shared/api/types";
import type { ChatMessage } from "../state";
import { APP_NAME } from "../../../shared/config/app";
import { ProjectRLogo } from "../../../shared/components/ProjectRLogo";
import { AgentIcon } from "../../../shared/icons/LineIcons";
import { renderMessageContent } from "../messageContent";
import type { SourcePreview } from "../messageContent";
import { MessageActions } from "./MessageActions";
import { MessageAgentRunCard } from "./MessageAgentRunCard";
import { MessageAttachments } from "./MessageAttachments";
import { ChatEmptyState } from "./ChatEmptyState";
import { ChatReplyLoadingMotion } from "./ChatReplyLoadingMotion";
import { MessageContextTraceCard } from "./MessageContextTraceCard";
import { MessageGeneratedFile } from "./MessageGeneratedFile";
import { MessageSkillRunCard } from "./MessageSkillRunCard";
import type { TextTransformAction } from "../textTransform";
import { buildLoadingStatusTexts } from "../loadingStatusTexts";
import { MessageSourceList } from "../../knowledge/components/MessageSourceList";

const COMPACT_META_GAP_MS = 5 * 60 * 1000;

export type ChatMessageListController = Record<string, any> & {
  apiOptions: ApiClientOptions;
  copiedMessageId: number | null;
  currentUser: { avatar?: string; nickname?: string | null } | null;
  editingDraft: string;
  editingMessageId: number | null;
  isActivePane: boolean;
  isEmptySplitPane: boolean;
  messageActionBusyId: number | null;
  messages: ChatMessage[];
  paneSessionId: number | null;
  scrollRef: RefObject<HTMLDivElement | null>;
  serverUrl: string;
  sessionIsSending: boolean;
  token: string | null;
  activeWorkspace?: WorkspaceResponse | null;
  onCopyGeneratedEmailBody?: (file: GeneratedFileResponse) => Promise<void>;
  onOpenGeneratedEmailClient?: (file: GeneratedFileResponse) => void;
  onSaveGeneratedFileToWorkspace?: (file: GeneratedFileResponse) => Promise<{ path: string }>;
  onEditGeneratedEmailDraft?: (file: GeneratedFileResponse) => void;
  onTransformMessage?: (message: ChatMessage, action: TextTransformAction) => void;
  onFocusComposer?: () => void;
};

export type ChatMessageListProps = {
  controller: ChatMessageListController;
};

function shouldCompactMessageMeta(messages: ChatMessage[], index: number) {
  if (index <= 0) return false;
  const current = messages[index];
  const previous = messages[index - 1];
  if (current.role !== previous.role) return false;
  const currentTime = Date.parse(current.created_at);
  const previousTime = Date.parse(previous.created_at);
  if (!Number.isFinite(currentTime) || !Number.isFinite(previousTime)) return false;
  return currentTime - previousTime < COMPACT_META_GAP_MS;
}

export function ChatMessageList({ controller }: ChatMessageListProps) {
  const {
    activeWorkspace,
    apiOptions,
    copiedMessageId,
    currentUser,
    editingDraft,
    editingMessageId,
    formatClockTime,
    handleActivateVersion,
    handleCopyMessage,
    handleExportConversation,
    handleSetBinaryFeedback,
    handleSubmitEditedMessage,
    handleSubmitGBrainThinkReview,
    handleSwitchToAgent,
    isActivePane,
    isEmptySplitPane,
    messageActionBusyId,
    messages,
    mode,
    openRegenerateDialog,
    onCopyGeneratedEmailBody,
    onEditGeneratedEmailDraft,
    onOpenGeneratedEmailClient,
    onSaveGeneratedFileToWorkspace,
    onTransformMessage,
    onFocusComposer,
    paneSessionId,
    renderAvatar,
    requestDeleteMessageContext,
    scrollRef,
    serverUrl,
    sessionIsSending,
    setEditingDraft,
    setEditingMessageId,
    setSourcePreview,
    setUtilityPanel,
    startEditingMessage,
    token,
  } = controller;

  function getLoadingStatusTexts(variant: "reply" | "regenerate") {
    const latestUserMessage = [...messages].reverse().find((message) => message.role === "user") as any;
    const latestContent = String(latestUserMessage?.content ?? "").trim();
    const activeSkillName = (controller as any).selectedSkill?.display_name
      || (controller as any).selectedSkill?.name
      || null;

    return buildLoadingStatusTexts({
      mode,
      variant,
      hasAttachments: Array.isArray(latestUserMessage?.attachments) && latestUserMessage.attachments.length > 0,
      isKnowledgeQuery: latestContent.startsWith("/query"),
      activeSkillName: activeSkillName ? String(activeSkillName) : null,
      webSearchEnabled: Boolean((controller as any).webSearchEnabled),
      thinkingEnabled: Boolean((controller as any).thinkingEnabled),
    });
  }

  function ReplyLoadingContent({
    inline = false,
    variant = "reply",
  }: {
    inline?: boolean;
    variant?: "reply" | "regenerate";
  }) {
    const [stepIndex, setStepIndex] = useState(0);
    const statusTexts = getLoadingStatusTexts(variant);
    const statusTextKey = statusTexts.join("\u0000");

    useEffect(() => {
      setStepIndex(0);
    }, [statusTextKey, variant]);

    useEffect(() => {
      const interval = window.setInterval(() => {
        setStepIndex((value) => (value + 1) % statusTexts.length);
      }, 2000);
      return () => window.clearInterval(interval);
    }, [statusTexts.length, statusTextKey]);

    return (
      <div className={`loading-placeholder-inner ${inline ? "loading-placeholder-inline" : ""}`}>
        <ChatReplyLoadingMotion />
        <span className="loading-placeholder-text">{statusTexts[stepIndex]}</span>
      </div>
    );
  }

  function LoadingPlaceholder() {
    return (
      <article className="message-row message-row-assistant message-row-loading">
        <span className="message-avatar assistant-avatar"><ProjectRLogo /></span>
        <div className="message-body">
          <div className="message-meta">
            <div className="message-name-line">
              <span className="message-role-label">{APP_NAME}</span>
            </div>
          </div>
          <div className="message-bubble">
            <ReplyLoadingContent />
          </div>
        </div>
      </article>
    );
  }

  function renderEmptyState(isSplitPane: boolean) {
    return (
      <ChatEmptyState
        activeWorkspace={activeWorkspace}
        isSplitPane={isSplitPane}
        mode={mode}
        onFocusComposer={onFocusComposer}
      />
    );
  }

  function renderMessageVersionBar(message: ChatMessage) {
    const versions = message.versions?.length ? message.versions : [];
    if (versions.length <= 1) return null;
    const activeIndex = Math.max(0, versions.findIndex((version) => version.active_version || version.id === message.id));
    const previous = versions[Math.max(0, activeIndex - 1)];
    const next = versions[Math.min(versions.length - 1, activeIndex + 1)];
    const isBusy = messageActionBusyId === message.id;
    return (
      <div className="message-version-bar">
        <button
          className="message-version-btn"
          disabled={activeIndex <= 0 || isBusy}
          onClick={() => previous ? void handleActivateVersion(message, previous) : undefined}
          type="button"
        >
          &lt;
        </button>
        <span>{activeIndex + 1} / {versions.length}</span>
        <button
          className="message-version-btn"
          disabled={activeIndex >= versions.length - 1 || isBusy}
          onClick={() => next ? void handleActivateVersion(message, next) : undefined}
          type="button"
        >
          &gt;
        </button>
      </div>
    );
  }

  function renderMessageCard(message: ChatMessage, messageIndex: number) {
    const isEditing = editingMessageId === message.id;
    const isBusy = messageActionBusyId === message.id;
    const hasMessageBubble = Boolean(message.content.trim()) || Boolean(message.isTyping) || Boolean(message.isRegenerating);
    const compactMeta = shouldCompactMessageMeta(filteredMessages, messageIndex);
    return (
      <article className={`message-row message-row-${message.role} ${message.status === "failed" ? "message-row-failed" : ""} ${compactMeta ? "message-row-compact" : ""}`} key={message.id}>
        {message.role === "assistant" ? (
          <span className="message-avatar assistant-avatar"><ProjectRLogo /></span>
        ) : (
          renderAvatar(currentUser?.avatar, currentUser?.nickname, 30, serverUrl)
        )}
        <div className="message-body">
          <div className="message-meta">
            <div className="message-name-line">
              <span className="message-role-label">{message.role === "user" ? currentUser?.nickname ?? "你" : APP_NAME}</span>
              {message.role === "assistant" && message.model ? <span className="model-badge">{message.model}</span> : null}
              <time className="message-time">{formatClockTime(message.created_at)}</time>
            </div>
          </div>
          {isEditing ? (
            <div className="message-edit-box">
              <textarea
                autoFocus
                onChange={(event) => setEditingDraft(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                    event.preventDefault();
                    void handleSubmitEditedMessage(message);
                  }
                  if (event.key === "Escape") {
                    setEditingMessageId(null);
                    setEditingDraft("");
                  }
                }}
                value={editingDraft}
              />
              <div className="message-edit-actions">
                <span>Ctrl + Enter 提交</span>
                <button className="btn-secondary" onClick={() => {
                  setEditingMessageId(null);
                  setEditingDraft("");
                }} type="button">取消</button>
                <button className="btn-primary" disabled={isBusy || !editingDraft.trim()} onClick={() => void handleSubmitEditedMessage(message)} type="button">
                  提交
                </button>
              </div>
            </div>
          ) : (
            <>
              <MessageAttachments attachments={message.attachments} apiOptions={apiOptions} />
              {hasMessageBubble ? (
                <div className="message-bubble">
                  {message.isRegenerating ? (
                    <ReplyLoadingContent inline variant="regenerate" />
                  ) : message.isTyping && !message.content.trim() ? (
                    <ReplyLoadingContent inline />
                  ) : (
                    renderMessageContent(message.content, message.sources ?? [], (preview) => {
                      setSourcePreview({ ...preview, contextTrace: message.context_trace, sessionId: message.session_id });
                      setUtilityPanel("source");
                    })
                  )}
                  {message.isTyping && !message.isRegenerating && message.content.trim() ? <span className="typing-caret" /> : null}
                </div>
              ) : null}
            </>
          )}
          {renderMessageVersionBar(message)}
          <MessageSourceList
            contextTrace={message.context_trace}
            sessionId={message.session_id}
            sources={message.sources}
            onSelectSource={(preview) => {
              setSourcePreview(preview);
              setUtilityPanel("source");
            }}
          />
          {message.generated_file ? (
            <MessageGeneratedFile
              activeWorkspace={activeWorkspace}
              file={message.generated_file}
              onCopyEmailBody={onCopyGeneratedEmailBody}
              onEditEmailDraft={onEditGeneratedEmailDraft}
              onOpenEmailClient={onOpenGeneratedEmailClient}
              onSaveToWorkspace={onSaveGeneratedFileToWorkspace}
              serverUrl={serverUrl}
              token={token}
            />
          ) : null}
          {message.role === "assistant" && (message.context_trace || message.agent_run || message.skill_run) ? (
            <div className="message-execution-stack">
              <MessageContextTraceCard
                collapseByDefault={!message.isTyping && !message.isRegenerating}
                contextTrace={message.context_trace}
                gbrainThinkReviewBusy={messageActionBusyId === message.id}
                messageSourceCount={message.sources?.length ?? 0}
                onSubmitGBrainThinkReview={message.context_trace?.gbrain_think
                  ? () => void handleSubmitGBrainThinkReview(message)
                  : undefined}
              />
              {message.agent_run
                && !(
                  message.skill_run
                  && ["completed", "failed"].includes(message.skill_run.status)
                  && ["completed", "failed"].includes(message.agent_run.status)
                )
                ? <MessageAgentRunCard agentRun={message.agent_run} />
                : null}
              {message.skill_run ? (
                <MessageSkillRunCard
              showGeneratedFile={!message.generated_file}
              skillRun={message.skill_run}
              onCopyGeneratedEmailBody={onCopyGeneratedEmailBody}
              onEditGeneratedEmailDraft={onEditGeneratedEmailDraft}
              onOpenGeneratedEmailClient={onOpenGeneratedEmailClient}
              onSaveGeneratedFileToWorkspace={onSaveGeneratedFileToWorkspace}
              serverUrl={serverUrl}
              token={token}
              workspace={activeWorkspace}
            />
              ) : null}
            </div>
          ) : null}
          {message.agent_suggestion ? (
            <div className="message-agent-suggestion">
              <div className="message-agent-suggestion-copy">
                <strong>建议切换到 Agent</strong>
                <span>{message.agent_suggestion.reason}</span>
              </div>
              <button
                className="message-agent-suggestion-btn"
                onClick={() => handleSwitchToAgent(message.id)}
                type="button"
              >
                <AgentIcon />
                <span>切换</span>
              </button>
            </div>
          ) : null}
          {message.role === "assistant" && message.feedback ? (
            <div className="message-feedback-status">
              <span>{message.feedback === "like" ? "已喜欢" : "已不喜欢"}</span>
              {message.feedback_comment ? <small>含意见</small> : null}
            </div>
          ) : null}
          <MessageActions
            copied={copiedMessageId === message.id}
            isBusy={isBusy}
            message={message}
            onActivateVersion={handleActivateVersion}
            onCopy={(target) => void handleCopyMessage(target)}
            onDelete={requestDeleteMessageContext}
            onExportConversation={(sessionId) => void handleExportConversation(sessionId)}
            onFeedback={(target, feedback) => void handleSetBinaryFeedback(target, feedback)}
            onQuote={(target) => controller.setQuotedMessage({ messageId: target.id, sessionId: paneSessionId!, content: target.content ?? "", role: target.role })}
            onRegenerate={openRegenerateDialog}
            onStartEdit={startEditingMessage}
            onSwitchToAgent={handleSwitchToAgent}
            onTransform={onTransformMessage}
          />
          {message.status === "failed" ? <p className="message-error">AI 服务暂时不可用</p> : null}
        </div>
      </article>
    );
  }

  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const isSearching = showSearch && searchQuery.trim().length > 0;
  const query = searchQuery.trim().toLowerCase();
  const filteredMessages = isSearching
    ? messages.filter((msg) => (msg.content ?? "").toLowerCase().includes(query))
    : messages;
  const hasPendingAssistantReply = messages.some(
    (message) => message.role === "assistant" && (message.isTyping || message.isRegenerating),
  );

  function handleToggleSearch() {
    setShowSearch((prev) => !prev);
    if (!showSearch) setSearchQuery("");
  }

  // Ctrl+F / Cmd+F 打开本地会话搜索（仅活跃面板响应）
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!isActivePane) return;
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea") return; // 输入框中不拦截
        e.preventDefault();
        handleToggleSearch();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isActivePane]);

  return (
    <div className="message-scroll" ref={isActivePane ? scrollRef : undefined}>
      {showSearch ? (
        <div className="session-search-bar">
          <input
            autoFocus
            className="session-search-input"
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") { setShowSearch(false); setSearchQuery(""); } }}
            placeholder="搜索当前会话…"
            type="text"
            value={searchQuery}
          />
          <span className="session-search-count">
            {filteredMessages.length}/{messages.length}
          </span>
          <button className="session-search-close" onClick={() => { setShowSearch(false); setSearchQuery(""); }} type="button">✕</button>
        </div>
      ) : messages.length > 10 ? (
        <div className="session-search-bar" style={{ justifyContent: "flex-end", background: "transparent", border: "none", padding: "2px 12px" }}>
          <button
            className="icon-button"
            onClick={handleToggleSearch}
            title="搜索当前会话 (Ctrl+F)"
            type="button"
            style={{ fontSize: 13 }}
          >
            🔍
          </button>
        </div>
      ) : null}
      {messages.length === 0 ? renderEmptyState(isEmptySplitPane) : null}
      {filteredMessages.map((message, index) => renderMessageCard(message, index))}
      {paneSessionId && sessionIsSending && !hasPendingAssistantReply ? <LoadingPlaceholder /> : null}
    </div>
  );
}
