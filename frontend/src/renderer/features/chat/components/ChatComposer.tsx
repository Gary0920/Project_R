import { useCallback, useEffect } from "react";
import type { ClipboardEvent, DragEvent, KeyboardEvent, RefObject } from "react";

import type { SkillResponse } from "../../../shared/api/types";
import {
  AgentIcon,
  BrainIcon,
  ChevronDownIcon,
  GlobeIcon,
  PaperclipIcon,
  PromptIcon,
  SendIcon,
  SettingsIcon,
  StopIcon,
  XmarkIcon,
} from "../../../shared/icons/LineIcons";

type SplitPaneKey = "left" | "right";

type ChatComposerController = Record<string, any> & {
  composerRef: RefObject<HTMLDivElement | null>;
  draft: string;
  fileInputRef: RefObject<HTMLInputElement | null>;
  isActivePane: boolean;
  paneSessionId: number | null;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
};

export type ChatComposerProps = {
  controller: ChatComposerController;
};

export function ChatComposer({ controller }: ChatComposerProps) {
  const {
    attachmentSourceLabel,
    authorizeLocalPrivateAttachments,
    clearPromptSelection,
    clearSelectedSkillIfMissing,
    composerRef,
    draft,
    fileInputRef,
    formatAttachmentSize,
    getSkillScopeLabel,
    handleCancelSend,
    handleChoosePrivateWorkspaceFiles,
    handleComposerPaste,
    handleKeyDown,
    handleRemovePendingAttachment,
    handleSelectAttachmentFiles,
    handleSend,
    insertSlashCandidate,
    isActivePane,
    isLocalPrivatePendingAttachment,
    isUploadingAttachments,
    mode,
    modelConfigError,
    modelMenuOpen,
    modelOptions,
    modelsLoading,
    paneSessionId,
    pendingAttachmentKey,
    pendingAttachmentSendFormLabel,
    pendingAttachmentStatusLabel,
    pendingAttachmentTargetLabel,
    pendingAttachments,
    selectedBuiltinCommand,
    selectedModelOption,
    selectedPrompt,
    selectedPromptIsDefault,
    selectedSkill,
    sendingSessions,
    setDraft,
    setModelMenuOpen,
    setSelectedBuiltinCommand,
    setSelectedModelKey,
    setSelectedSkill,
    setSkillPanelIndex,
    setUtilityPanel,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
    syncSlashCommand,
    textareaRef,
    toggleWebSearch,
    temperature,
    setTemperature,
    thinkingEnabled,
    utilityPanel,
    webSearchEnabled,
    setThinkingEnabled,
    modelSelectRef,
    activeSessionTokenTotal,
  } = controller;

  // C6: 输入框随内容自动调整高度
  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxH = 240; // 与 CSS .composer textarea max-height 一致
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
  }, [textareaRef]);
  useEffect(() => { resizeTextarea(); }, [draft, resizeTextarea, isActivePane]);

    if (!isActivePane) {
      return <div className="composer-inactive-hint">点击此侧后继续输入</div>;
    }
    const sessionIsSending = paneSessionId ? Boolean(sendingSessions[paneSessionId]) : false;
    const localPrivateAttachments = (pendingAttachments as any[]).filter(isLocalPrivatePendingAttachment);
    const unauthorizedLocalAttachmentCount = localPrivateAttachments.filter((attachment: any) => attachment.authorization_status !== "authorized").length;
    const hasUnauthorizedLocalAttachments = unauthorizedLocalAttachmentCount > 0;
    const hasLocalPrivateImages = localPrivateAttachments.some((attachment: any) => attachment.kind === "image");
    const canSendMessage = Boolean(draft.trim() || pendingAttachments.length) && !hasUnauthorizedLocalAttachments;
    const sendButtonTitle = sessionIsSending
      ? "停止生成 (Esc)"
      : hasUnauthorizedLocalAttachments
        ? "请先确认本机选择文件"
        : "发送";
    const attachmentButtonLabel = isUploadingAttachments
      ? "附件处理中"
      : "添加附件";
    const handleAttachmentButtonClick = () => {
      if (window.projectR?.privateWorkspace) {
        void handleChoosePrivateWorkspaceFiles();
        return;
      }
      fileInputRef.current?.click();
    };
    return (
      <div className="composer-wrap">
        <div className="composer" ref={composerRef}>
          {localPrivateAttachments.length ? (
            <div className={`composer-attachment-consent ${hasUnauthorizedLocalAttachments ? "is-pending" : "is-authorized"}`}>
              <div className="composer-attachment-consent-copy">
                  <strong>本机选择文件</strong>
                <span>
                  {hasUnauthorizedLocalAttachments
                    ? `${unauthorizedLocalAttachmentCount} 个文件来自本机选择，发送前需确认。Chat 模式文本默认只发送摘录；Agent 模式会把选中文件作为后端临时文件处理。${hasLocalPrivateImages ? " 图片确认后会上传给后端模型链路用于多模态理解。" : ""}`
                    : "已确认本次发送授权；这些文件不会自动进入项目资料或公司知识库。"}
                </span>
              </div>
              <button
                disabled={!hasUnauthorizedLocalAttachments}
                onClick={authorizeLocalPrivateAttachments}
                type="button"
              >
                {hasUnauthorizedLocalAttachments ? "确认本次发送" : "已确认"}
              </button>
            </div>
          ) : null}
          {pendingAttachments.length ? (
            <div className="composer-attachments">
              {(pendingAttachments as any[]).map((attachment: any) => {
                const attachmentMeta = [
                  attachmentSourceLabel(attachment),
                  pendingAttachmentStatusLabel(attachment),
                  pendingAttachmentSendFormLabel(attachment, mode),
                  pendingAttachmentTargetLabel(mode),
                  formatAttachmentSize(attachment.size),
                ].filter(Boolean);
                return (
                  <div
                    className={`composer-attachment-chip is-${attachment.kind} is-${attachment.source_scope} ${attachment.authorization_status === "authorized" ? "is-authorized" : ""}`}
                    key={pendingAttachmentKey(attachment)}
                    title={attachment.original_name}
                  >
                    <span className="composer-attachment-badge">{attachment.input_source === "workspace_reference" ? "引用" : "附件"}</span>
                    {attachment.previewUrl ? (
                      <img alt={attachment.original_name} className="composer-attachment-thumb" src={attachment.previewUrl} />
                    ) : (
                      <span className="composer-attachment-kind">
                        {attachment.kind === "pdf" ? "PDF" : attachment.kind === "text" ? "TXT" : <PaperclipIcon />}
                      </span>
                    )}
                    <span className="composer-attachment-name">{attachment.original_name}</span>
                    <small className="composer-attachment-meta">
                      {attachmentMeta.map((item: string) => <span key={`${pendingAttachmentKey(attachment)}-${item}`}>{item}</span>)}
                    </small>
                    {attachment.preprocess?.summary ? (
                      <em>{attachment.preprocess.summary}</em>
                    ) : null}
                    <button
                      aria-label={`移除附件：${attachment.original_name}`}
                      className="composer-attachment-remove"
                      onClick={() => void handleRemovePendingAttachment(attachment)}
                      title="移除附件"
                      type="button"
                    >
                      <XmarkIcon />
                    </button>
                  </div>
                );
              })}
            </div>
          ) : null}
          {isUploadingAttachments ? <div className="composer-uploading">附件处理中</div> : null}
          {(!selectedPromptIsDefault || selectedSkill || selectedBuiltinCommand) ? (
            <div className="composer-context-row">
              {!selectedPromptIsDefault ? (
                <button
                  className="composer-context-chip composer-context-chip-prompt"
                  onClick={clearPromptSelection}
                  title="移除提示词"
                  type="button"
                >
                  <span className="composer-context-chip-icon"><PromptIcon /></span>
                  <strong>{selectedPrompt.name}</strong>
                  <small>提示词</small>
                </button>
              ) : null}
              {selectedBuiltinCommand ? (
                <button
                  className="composer-context-chip composer-context-chip-command"
                  onClick={() => {
                    setSelectedBuiltinCommand(null);
                    textareaRef.current?.focus();
                  }}
                  title="移除内置命令"
                  type="button"
                >
                  <span className="composer-context-chip-icon">/</span>
                  <strong>{selectedBuiltinCommand.displayName}</strong>
                  <small>内置命令</small>
                </button>
              ) : null}
              {selectedSkill ? (
                <button
                  className="composer-context-chip composer-context-chip-skill"
                  onClick={() => {
                    setSelectedSkill(null);
                    textareaRef.current?.focus();
                  }}
                  title="移除 Skill"
                  type="button"
                >
                  <span className="composer-context-chip-icon">/</span>
                  <strong>{selectedSkill.display_name}</strong>
                  <small>{getSkillScopeLabel(selectedSkill)}</small>
                </button>
              ) : null}
            </div>
          ) : null}
          {skillPanelVisible ? (
            <div className="skill-candidate-panel" role="listbox">
              <div className="skill-candidate-panel-header">
                <span>选择指令或 Skill</span>
                <kbd>/</kbd>
              </div>
              {slashCandidates.length > 0 ? (
                (slashCandidates as any[]).map((candidate: any, index: number) => {
                  const isCommand = candidate.kind === "command";
                  const label = isCommand ? candidate.command.displayName : candidate.skill.display_name;
                  const description = isCommand ? candidate.command.description : candidate.skill.description;
                  const scope = isCommand ? candidate.command.scope : getSkillScopeLabel(candidate.skill);
                  const key = isCommand ? `command-${candidate.command.name}` : `skill-${candidate.skill.name}`;
                  return (
                  <button
                    key={key}
                    className={`skill-candidate-item ${index === skillPanelIndex ? "is-active" : ""}`}
                    onClick={() => insertSlashCandidate(candidate)}
                    onMouseEnter={() => setSkillPanelIndex(index)}
                    role="option"
                    type="button"
                  >
                    <span className="skill-candidate-icon">{isCommand ? "/" : "S"}</span>
                    <span className="skill-candidate-copy">
                      <span className="skill-candidate-title">
                        <strong>{label}</strong>
                        <span>{description}</span>
                      </span>
                    </span>
                    <span className="skill-candidate-scope">{scope}</span>
                  </button>
                  );
                })
              ) : (
                <div className="skill-candidate-empty">没有匹配的指令或 Skill</div>
              )}
            </div>
          ) : null}
          <textarea
            onChange={(event) => {
              const value = event.target.value;
              const caret = event.target.selectionStart ?? value.length;
              setDraft(value);
              clearSelectedSkillIfMissing(value);
              syncSlashCommand(value, caret);
            }}
            onClick={(event) => syncSlashCommand(event.currentTarget.value, event.currentTarget.selectionStart ?? event.currentTarget.value.length)}
            onKeyDown={handleKeyDown}
            onPaste={handleComposerPaste}
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            ref={textareaRef}
            rows={1}
            value={draft}
          />
          {activeSessionTokenTotal != null && activeSessionTokenTotal > 0 ? (
            <div className="composer-token-hint">{activeSessionTokenTotal} tokens</div>
          ) : null}
          <div className="composer-toolbar">
            <div className="composer-left-tools">
              <input
                className="hidden-file-input"
                multiple
                onChange={(event) => void handleSelectAttachmentFiles(event.target.files)}
                ref={fileInputRef}
                type="file"
              />
              <button
                className="composer-tool-icon"
                data-tooltip={attachmentButtonLabel}
                disabled={isUploadingAttachments}
                onClick={handleAttachmentButtonClick}
                title="添加附件"
                type="button"
              >
                <PaperclipIcon />
              </button>
              <div className="composer-config-group" aria-label="模型配置">
                <div className="composer-model-select" ref={modelSelectRef}>
                  <button
                    aria-label={`选择模型：${selectedModelOption?.label ?? (modelsLoading ? "加载模型" : "选择模型")}`}
                    aria-expanded={modelMenuOpen}
                    className="composer-model-button"
                    data-tooltip="切换模型"
                    onClick={() => setModelMenuOpen((value: boolean) => !value)}
                    title="选择模型"
                    type="button"
                  >
                    <SettingsIcon />
                    <span className="composer-model-label">{selectedModelOption?.label ?? (modelsLoading ? "加载模型" : "选择模型")}</span>
                    <ChevronDownIcon />
                  </button>
                  {modelMenuOpen ? (
                    <div className="model-dropdown-menu" role="listbox" aria-label="选择模型">
                      <div className="menu-group-title">已配置模型</div>
                      <div className="menu-items-list">
                        {(modelOptions as any[]).map((option: any) => {
                          const selected = option.key === selectedModelOption?.key;
                          return (
                            <div
                              aria-selected={selected}
                              className={`menu-item ${selected ? "active" : ""}`}
                              key={option.key}
                              onClick={() => {
                                setSelectedModelKey(option.key);
                                setModelMenuOpen(false);
                                textareaRef.current?.focus();
                              }}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") {
                                  event.preventDefault();
                                  setSelectedModelKey(option.key);
                                  setModelMenuOpen(false);
                                  textareaRef.current?.focus();
                                }
                              }}
                              role="option"
                              tabIndex={0}
                            >
                              <div className="item-text-container">
                                <div className="item-title">{option.label}</div>
                                <div className="item-description">{option.description}</div>
                              </div>
                              {selected ? <div className="item-check-icon" aria-hidden="true">✓</div> : null}
                            </div>
                          );
                        })}
                        {modelsLoading ? (
                          <div className="model-menu-empty">读取模型配置</div>
                        ) : null}
                        {!modelsLoading && modelOptions.length === 0 ? (
                          <div className="model-menu-empty">{modelConfigError || "暂无已配置模型"}</div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="composer-mode-toggles" aria-label="对话增强开关">
                  <button
                    aria-label={thinkingEnabled ? "关闭深度思考" : "开启深度思考"}
                    aria-pressed={thinkingEnabled}
                    className={`composer-mode-toggle is-thinking ${thinkingEnabled ? "is-active" : ""}`}
                    data-tooltip={thinkingEnabled ? "关闭深度思考" : "开启深度思考"}
                    onClick={() => setThinkingEnabled((value: boolean) => !value)}
                    title="深度思考"
                    type="button"
                  >
                    <BrainIcon />
                    <span className="composer-button-label">深度思考</span>
                  </button>
                  <button
                    aria-label={webSearchEnabled ? "关闭联网搜索" : "开启联网搜索"}
                    aria-pressed={webSearchEnabled}
                    className={`composer-mode-toggle is-search ${webSearchEnabled ? "is-active" : ""}`}
                    data-tooltip={webSearchEnabled ? "关闭联网搜索" : "开启联网搜索"}
                    onClick={toggleWebSearch}
                    title="联网搜索"
                    type="button"
                  >
                    <GlobeIcon />
                    <span className="composer-button-label">联网搜索</span>
                  </button>
                </div>
                <div className="composer-temp-slider">
                  <input
                    aria-label="创意度"
                    className="composer-temp-input"
                    max="2"
                    min="0"
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    step="0.1"
                    title={`创意度: ${temperature ?? 0.7}`}
                    type="range"
                    value={temperature ?? 0.7}
                  />
                </div>
              </div>
            </div>
            <div className="composer-right-tools">
              <div className="composer-toolbox-group" aria-label="Agent 工具箱">
                <button
                  aria-label="提示词"
                  className={`composer-tool-button ${utilityPanel === "prompt" ? "is-active" : ""}`}
                  data-tooltip="提示词"
                  onClick={() => setUtilityPanel((value: string | null) => value === "prompt" ? null : "prompt")}
                  title={`提示词：${selectedPrompt.name}`}
                  type="button"
                >
                  <PromptIcon />
                  <span className="composer-button-label">提示词</span>
                </button>
                <button
                  aria-label="技能"
                  className={`composer-tool-button ${utilityPanel === "skills" ? "is-active" : ""}`}
                  data-tooltip="Skills"
                  onClick={() => setUtilityPanel((value: string | null) => value === "skills" ? null : "skills")}
                  title="Skills"
                  type="button"
                >
                  <AgentIcon />
                  <span className="composer-button-label">技能</span>
                </button>
              </div>
              <button
                className={`composer-send ${sessionIsSending ? "is-stopping" : ""}`}
                disabled={(!canSendMessage && !sessionIsSending) || isUploadingAttachments}
                onClick={() => sessionIsSending ? handleCancelSend(paneSessionId) : void handleSend()}
                title={sendButtonTitle}
                type="button"
              >
                {sessionIsSending ? <StopIcon /> : <SendIcon />}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
}
