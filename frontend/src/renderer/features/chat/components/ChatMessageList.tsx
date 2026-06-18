import { useEffect, useState, type RefObject } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import type {
  ChatContextTraceResponse,
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
import { MessageGeneratedFile } from "./MessageGeneratedFile";
import { MessageSkillRunCard } from "./MessageSkillRunCard";
import type { TextTransformAction } from "../textTransform";
import { MessageSourceList } from "../../knowledge/components/MessageSourceList";

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
};

export type ChatMessageListProps = {
  controller: ChatMessageListController;
};

function _isDefaultPromptId(promptId: string | null | undefined) {
  return promptId === "builtin:builtin-project-r";
}

function hasContextTrace(contextTrace: ChatContextTraceResponse | null | undefined) {
  if (!contextTrace) return false;
  const hasVisiblePrompt = contextTrace.prompt?.system_prompt_provided
    || (contextTrace.prompt?.selected_prompt_id && !_isDefaultPromptId(contextTrace.prompt.selected_prompt_id));
  return Boolean(
    contextTrace.attachments?.length ||
    contextTrace.knowledge?.source_count ||
    hasVisiblePrompt ||
    contextTrace.skill?.skill_name ||
    contextTrace.gbrain_think?.gap_count ||
    contextTrace.gbrain_think?.conflict_count ||
    contextTrace.gbrain_think?.warning_count ||
    contextTrace.model?.model,
  );
}

function renderContextTraceCard(
  contextTrace: ChatContextTraceResponse | null | undefined,
  options: { onSubmitGBrainThinkReview?: () => void; gbrainThinkReviewBusy?: boolean } = {},
) {
  if (!hasContextTrace(contextTrace) || !contextTrace) return null;
  const attachments = contextTrace.attachments ?? [];
  const sources = contextTrace.knowledge?.sources ?? [];
  const prompt = contextTrace.prompt;
  const model = contextTrace.model;
  const gbrainThink = contextTrace.gbrain_think;
  const gbrainGaps = gbrainThink?.gaps?.filter(Boolean) ?? [];
  const gbrainConflicts = gbrainThink?.conflicts?.filter(Boolean) ?? [];
  const gbrainWarnings = gbrainThink?.warnings?.filter(Boolean) ?? [];
  const modelBadges = [
    model?.model,
    model?.thinking ? "思考" : null,
    model?.web_search ? "联网搜索" : null,
  ].filter(Boolean).join(" · ");
  return (
    <div className="message-context-trace">
      <div className="message-context-trace-header">
        <strong>本轮上下文</strong>
        {modelBadges ? <span>{modelBadges}</span> : null}
      </div>
      <div className="message-context-trace-grid">
        {attachments.length ? (
          <div className="message-context-trace-section">
            <span>附件</span>
            {attachments.slice(0, 4).map((attachment) => (
              <small key={`${attachment.id}-${attachment.name}`}>{attachment.name ?? `附件 ${attachment.id}`}</small>
            ))}
            {attachments.length > 4 ? <small>另有 {attachments.length - 4} 个附件</small> : null}
          </div>
        ) : null}
        {sources.length || contextTrace.knowledge?.source_count ? (
          <div className="message-context-trace-section">
            <span>知识来源</span>
            {sources.slice(0, 4).map((source) => (
              <small key={`${source.index}-${source.file}`}>{source.section_path || source.source_title || source.file}</small>
            ))}
            {(contextTrace.knowledge?.source_count ?? 0) > sources.length ? (
              <small>共 {contextTrace.knowledge?.source_count} 个来源</small>
            ) : null}
          </div>
        ) : null}
        {gbrainThink && (gbrainGaps.length || gbrainConflicts.length || gbrainWarnings.length) ? (
          <div className="message-context-trace-section is-gbrain-think">
            <span>
              GBrain 推理状态
              {options.onSubmitGBrainThinkReview ? (
                <button
                  className="message-context-trace-action"
                  disabled={options.gbrainThinkReviewBusy}
                  onClick={options.onSubmitGBrainThinkReview}
                  type="button"
                >
                  {options.gbrainThinkReviewBusy ? "提交中" : "提交审核"}
                </button>
              ) : null}
            </span>
            {gbrainConflicts.length ? <small className="is-conflict">冲突 {gbrainConflicts.length} 条</small> : null}
            {gbrainGaps.length ? <small className="is-gap">缺口 {gbrainGaps.length} 条</small> : null}
            {gbrainWarnings.length ? <small className="is-warning">警告 {gbrainWarnings.length} 条</small> : null}
          </div>
        ) : null}
        {prompt?.system_prompt_provided || (prompt?.selected_prompt_id && !_isDefaultPromptId(prompt.selected_prompt_id)) ? (
          <div className="message-context-trace-section">
            <span>提示词</span>
            {prompt?.selected_prompt_id && !_isDefaultPromptId(prompt.selected_prompt_id) ? <small>{prompt.selected_prompt_id}</small> : null}
            {prompt?.system_prompt_provided ? <small>{prompt.system_prompt_preview || "已使用会话提示词"}</small> : null}
          </div>
        ) : null}
        {contextTrace.skill?.skill_name ? (
          <div className="message-context-trace-section">
            <span>Skill</span>
            <small>{contextTrace.skill.display_name || contextTrace.skill.skill_name}</small>
          </div>
        ) : null}
      </div>
    </div>
  );
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
    sideBySideOpen,
    startEditingMessage,
    token,
  } = controller;

  function getLoadingProcessSteps(isInline = false) {
    const latestUserMessage = [...messages].reverse().find((message) => message.role === "user") as any;
    const latestContent = String(latestUserMessage?.content ?? "").trim();
    // Skill from controller state (set when user selects a Skill before sending)
    const activeSkillName = (controller as any).selectedSkill?.display_name
      || (controller as any).selectedSkill?.name
      || null;

    if (mode === "agent") {
      if (activeSkillName) {
        const label = typeof activeSkillName === "string" ? activeSkillName : String(activeSkillName);
        return ["已选择 Skill：" + label, "正在读取上下文", "正在执行任务"];
      }
      return isInline
        ? ["正在整理执行步骤", "正在更新任务状态", "正在生成结果"]
        : ["正在理解任务目标", "正在整理执行计划", "正在准备步骤状态"];
    }
    const hasAttachments = Array.isArray(latestUserMessage?.attachments) && latestUserMessage.attachments.length > 0;
    if (latestContent.startsWith("/query")) {
      return ["正在识别知识库问题", "正在确认查询范围", "正在生成回答"];
    }
    if (hasAttachments) {
      return ["正在读取本轮附件", "正在整理上下文", "正在生成回答"];
    }
    return ["正在理解问题", "正在整理上下文", "正在生成回答"];
  }

  function LoadingPlaceholder() {
    const [stepIndex, setStepIndex] = useState(0);
    const processSteps = getLoadingProcessSteps();

    useEffect(() => {
      const interval = window.setInterval(() => {
        setStepIndex((value) => (value + 1) % processSteps.length);
      }, 2000);
      return () => window.clearInterval(interval);
    }, [processSteps.length]);

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
            <div className="loading-placeholder-inner">
              <svg className="pl" viewBox="0 0 128 128" width="128" height="128" xmlns="http://www.w3.org/2000/svg">
                <circle className="pl__ring pl__ring--a" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--b" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--c" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
                <circle className="pl__ring pl__ring--d" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
              </svg>
              <span className="loading-placeholder-text">{mode === "agent" ? "Agent 执行中" : "正在回复"}</span>
              <small className="loading-process-text">{processSteps[stepIndex]}</small>
            </div>
          </div>
        </div>
      </article>
    );
  }

  function InlineLoadingPlaceholder() {
    const [stepIndex, setStepIndex] = useState(0);
    const processSteps = getLoadingProcessSteps(true);

    useEffect(() => {
      const interval = window.setInterval(() => {
        setStepIndex((value) => (value + 1) % processSteps.length);
      }, 2000);
      return () => window.clearInterval(interval);
    }, [processSteps.length]);

    return (
      <div className="loading-placeholder-inner loading-placeholder-inline">
        <svg className="pl" viewBox="0 0 128 128" width="128" height="128" xmlns="http://www.w3.org/2000/svg">
          <circle className="pl__ring pl__ring--a" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--b" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--c" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
          <circle className="pl__ring pl__ring--d" cx="64" cy="64" r="56" fill="none" strokeWidth="16" transform="rotate(90,64,64)" />
        </svg>
        <span className="loading-placeholder-text">{mode === "agent" ? "执行中" : "生成中"}</span>
        <small className="loading-process-text">{processSteps[stepIndex]}</small>
      </div>
    );
  }

  function renderEmptyState(isSplitPane: boolean) {
    if (isSplitPane) {
      return (
        <div className="empty-chat empty-chat-compact">
          <span className="empty-chat-mark"><ProjectRLogo /></span>
          <h2>选择一个对话</h2>
          <p>先点击这个区域，再从左侧会话列表选择要放进来的对话。</p>
        </div>
      );
    }
    if (mode === "agent") {
      return (
        <div className={`empty-agent ${sideBySideOpen ? "is-split-mode" : ""}`}>
          <div className="empty-agent-copy">
            <span className="empty-chat-mark"><ProjectRLogo /></span>
            <h2>{activeWorkspace ? `在「${activeWorkspace.name}」开始 Agent` : "选择项目后开始 Agent"}</h2>
            <p>直接说明你要整理、核对或生成的业务结果。</p>
          </div>
        </div>
      );
    }
    return (
      <div className="empty-chat">
        <span className="empty-chat-mark"><ProjectRLogo /></span>
        <h2>{activeWorkspace ? `在「${activeWorkspace.name}」开始聊天` : "从一个问题开始"}</h2>
        <p>询问规范、整理资料，或把当前工作流交给 Project_R 梳理成可执行步骤。</p>
      </div>
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

  function renderMessageCard(message: ChatMessage) {
    const isEditing = editingMessageId === message.id;
    const isBusy = messageActionBusyId === message.id;
    const hasMessageBubble = Boolean(message.content.trim()) || Boolean(message.isTyping) || Boolean(message.isRegenerating);
    return (
      <article className={`message-row message-row-${message.role} ${message.status === "failed" ? "message-row-failed" : ""}`} key={message.id}>
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
                    <InlineLoadingPlaceholder />
                  ) : (
                    renderMessageContent(message.content, message.sources ?? [], (preview) => {
                      setSourcePreview({ ...preview, contextTrace: message.context_trace, sessionId: message.session_id });
                      setUtilityPanel("source");
                    })
                  )}
                  {message.isTyping && !message.isRegenerating ? <span className="typing-caret" /> : null}
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
          {message.role === "assistant" ? renderContextTraceCard(message.context_trace, {
            gbrainThinkReviewBusy: messageActionBusyId === message.id,
            onSubmitGBrainThinkReview: message.context_trace?.gbrain_think
              ? () => void handleSubmitGBrainThinkReview(message)
              : undefined,
          }) : null}
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
          {message.agent_run ? <MessageAgentRunCard agentRun={message.agent_run} /> : null}
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
      {filteredMessages.map(renderMessageCard)}
      {paneSessionId && sessionIsSending ? <LoadingPlaceholder /> : null}
    </div>
  );
}
