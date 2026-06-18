import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";

import { ApiError, type ApiClientOptions } from "../shared/api/client";
import { createApiOptions } from "../shared/api/options";
import { createChatSession, fetchSessionAttachmentBlob, listChatMessages, listChatSessions, searchChatSessions } from "../features/chat/api";
import { useChatDraft } from "../features/chat/useChatDraft";
import { getLLMHealth } from "../shared/api/health";
import type { NotificationView } from "../features/notifications/api";
import { listSkills } from "../features/skills/api";
import { authTokenAtom, clearAuthAtom, currentUserAtom } from "../features/auth/state";
import { parseApiDate } from "../shared/utils/time";
import {
  activeMessagesAtom,
  activeSessionAtom,
  activeSessionIdAtom,
  chatErrorAtom,
  chatLoadingAtom,
  chatMessagesBySessionAtom,
  chatSessionsAtom,
  type ChatMessage,
} from "../features/chat/state";
import { serverUrlAtom } from "../shared/state/server";
import { activeModeAtom } from "../shared/state/ui";
import { activeTabIdAtom, tabsAtom } from "../features/chat/tabs-state";
import { activeWorkspaceIdAtom, workspacesAtom } from "../features/workspace/state";
import { saveGeneratedFileToWorkspace } from "../features/workspace/api";
import {
  formatNotificationTime,
  notificationCategoryLabel,
} from "../features/notifications/formatters";
import type {
  ChatSearchResultResponse,
  ChatSessionResponse,
  ChatContextTraceResponse,
  AgentRunResponse,
  GeneratedFileResponse,
  LLMProviderStatusResponse,
  SkillResponse,
  SkillRunResponse,
} from "../shared/api/types";
import { APP_NAME } from "../shared/config/app";
import { useContextMenu, type ContextMenuItemDef } from "../shared/components/ContextMenu";
import { PromptPanel } from "../features/prompts/components/PromptPanel";
import { ScratchPad } from "../features/chat/components/ScratchPad";
import { SearchDialog } from "../features/chat/components/SearchDialog";
import { SettingsModal } from "../features/settings/components/SettingsModal";
import { TabBar } from "../features/chat/components/TabBar";
import { WorkspaceSelector } from "../features/workspace/components/WorkspaceSelector";
import { WorkspaceFilePanel } from "../features/workspace/components/WorkspaceFilePanel";
import { copyText } from "../features/chat/clipboard";
import { downloadGeneratedFile } from "../features/chat/generatedFiles";
import { EmailDraftEditor } from "../features/chat/components/EmailDraftEditor";
import { AppWorkspaceChrome } from "../features/chat/components/AppWorkspaceChrome";
import { ChatConversationPane } from "../features/chat/components/ChatConversationPane";
import type { SourcePreview } from "../features/chat/messageContent";
import { useGeneratedEmailDraftActions } from "../features/chat/useGeneratedEmailDraftActions";
import { useTextTransformActions } from "../features/chat/useTextTransformActions";
import {
  attachmentSourceLabel,
  formatAttachmentSize,
  isLocalPrivatePendingAttachment,
  pendingAttachmentKey,
  pendingAttachmentSendFormLabel,
  pendingAttachmentStatusLabel,
  pendingAttachmentTargetLabel,
} from "../features/chat/attachments";
import {
  UPDATE_DOWNLOAD_DRY_RUN,
  formatUpdateBytes,
  formatUpdateSpeed,
} from "../features/updates/clientVersion";
import {
  formatClockTime,
  formatSessionDisplayTitle,
  formatSidebarTime,
  getInitials,
  groupSessionsByTime,
  makeSessionTitle,
  renderAvatar,
  resolveAvatarUrl,
} from "../features/chat/sessionDisplay";
import { toModelOption } from "../features/chat/modelOptions";
import { makeLocalMessage } from "../features/chat/localMessages";
import { latestSessionTokenTotal } from "../features/chat/sessionMetrics";
import { readWebSearchPreference, shouldSuggestAgentMode, writeWebSearchPreference } from "../features/prompts/sessionPrompt";
import { useChatSendResults } from "../features/chat/useChatSend";
import { useChatSendOrchestrator } from "../features/chat/useChatSendOrchestrator";
import { useChatStreamControls } from "../features/chat/useChatStream";
import { useChatRegenerate } from "../features/chat/useChatRegenerate";
import { useChatGlobalShortcuts } from "../features/chat/useChatGlobalShortcuts";
import { useChatComposerShortcuts } from "../features/chat/useChatComposerShortcuts";
import { useNotificationCenter } from "../features/notifications/hooks/useNotificationCenter";
import { useClientUpdate } from "../features/updates/hooks/useClientUpdate";
import { useAppShellPanels } from "../features/chat/hooks/useAppShellPanels";
import { useChatAttachments } from "../features/chat/hooks/useChatAttachments";
import { useAppShellPointerDismiss } from "../features/chat/hooks/useAppShellPointerDismiss";
import { useChatMessageActions } from "../features/chat/hooks/useChatMessageActions";
import { useChatSessionManagement, type RenameScope } from "../features/chat/hooks/useChatSessionManagement";
import { useSlashCommandSelection } from "../features/chat/hooks/useSlashCommandSelection";
import { useAppPromptSelection } from "../features/chat/hooks/useAppPromptSelection";
type SplitPaneKey = "left" | "right";
type UtilityPanel = "workspace" | "knowledge" | "customer-intelligence" | "prompt" | "skills" | "source" | "crm";
type SettingsAdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";

export function AppPage() {
  const serverUrl = useAtomValue(serverUrlAtom);
  const token = useAtomValue(authTokenAtom);
  const currentUser = useAtomValue(currentUserAtom);
  const clearAuth = useSetAtom(clearAuthAtom);
  const [sessions, setSessions] = useAtom(chatSessionsAtom);
  const [activeSessionId, setActiveSessionId] = useAtom(activeSessionIdAtom);
  const activeSession = useAtomValue(activeSessionAtom);
  const activeMessages = useAtomValue(activeMessagesAtom);
  const [messagesBySession, setMessagesBySession] = useAtom(chatMessagesBySessionAtom);
  const [isLoading, setIsLoading] = useAtom(chatLoadingAtom);
  const [error, setError] = useAtom(chatErrorAtom);
  const [actionNotice, setActionNotice] = useState("");
  const [workspaceFilePanelRefreshKey, setWorkspaceFilePanelRefreshKey] = useState(0);
  const [draft, setDraft, clearCurrentDraft] = useChatDraft(activeSessionId);
  const [mode, setMode] = useAtom(activeModeAtom);
  const [tabs, setTabs] = useAtom(tabsAtom);
  const [activeTabId, setActiveTabId] = useAtom(activeTabIdAtom);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(readWebSearchPreference);
  const [temperature, setTemperature] = useState<number | undefined>(undefined);
  const [quotedMessage, setQuotedMessage] = useState<{ sessionId: number; messageId: number; content: string; role: string } | null>(null);
  // 切换会话时清空引用（防止 A 会话内容被发送到 B 会话）
  useEffect(() => {
    if (quotedMessage && quotedMessage.sessionId !== activeSessionId) {
      setQuotedMessage(null);
    }
  }, [activeSessionId, quotedMessage?.sessionId]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useAtom(activeWorkspaceIdAtom);
  const [workspaces] = useAtom(workspacesAtom);
  const [showScratchPad, setShowScratchPad] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; items: ContextMenuItemDef[] } | null>(null);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ChatSearchResultResponse[]>([]);
  const [utilityPanel, setUtilityPanel] = useState<UtilityPanel | null>(null);
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(null);
  const [sideBySideOpen, setSideBySideOpen] = useState(false);
  const [activeSplitPane, setActiveSplitPane] = useState<SplitPaneKey>("left");
  const [splitPaneSessionIds, setSplitPaneSessionIds] = useState<Record<SplitPaneKey, number | null>>({ left: null, right: null });
  const [sendingSessions, setSendingSessions] = useState<Record<number, boolean>>({});
  const { appendLegacyAssistantResponse, finalizeStreamAssistantResponse } = useChatSendResults({ setMessagesBySession });
  const { cancelSessionSend, finishSessionSend, registerSendAbortController, removeStreamPlaceholder, setSessionSending, typeAssistantReply, updateStreamPlaceholder } =
    useChatStreamControls({ setMessagesBySession, setSendingSessions });
  const [emailDraftEditorFile, setEmailDraftEditorFile] = useState<GeneratedFileResponse | null>(null);
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [llmProviders, setLlmProviders] = useState<LLMProviderStatusResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelConfigError, setModelConfigError] = useState("");
  const [selectedModelKey, setSelectedModelKey] = useState<string | null>(null);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsInitialAdminTab, setSettingsInitialAdminTab] = useState<SettingsAdminTab | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const titleInputRef = useRef<HTMLInputElement | null>(null);
  const sidebarRenameInputRef = useRef<HTMLInputElement | null>(null);
  const composerRef = useRef<HTMLDivElement | null>(null);
  const modelSelectRef = useRef<HTMLDivElement | null>(null);
  const notificationPanelRef = useRef<HTMLDivElement | null>(null);
  const notificationButtonRef = useRef<HTMLButtonElement | null>(null);

  const apiOptions = useMemo(
    () => createApiOptions(serverUrl, token, clearAuth),
    [clearAuth, serverUrl, token],
  );
  const {
    clearPromptSelection,
    companyPrompts,
    defaultPromptId,
    handleCreateUserPrompt,
    handleDeleteUserPrompt,
    handleSelectPrompt,
    pendingPromptId,
    promptOptions,
    selectedPrompt,
    selectedPromptId,
    selectedPromptIsDefault,
    setPendingPromptId,
    storePromptSelection,
    userPrompts,
  } = useAppPromptSelection({
    activeSessionId,
    apiOptions,
    setUtilityPanel,
    textareaRef,
  });
  const {
    clearSelectedSkillIfMissing,
    insertSlashCandidate,
    selectedBuiltinCommand,
    selectedSkill,
    setSelectedBuiltinCommand,
    setSelectedSkill,
    setSkillPanelIndex,
    setSkillPanelVisible,
    setSlashCommand,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
    slashCommand,
    syncSlashCommand,
  } = useSlashCommandSelection({
    draft,
    mode,
    setDraft,
    setMode,
    skills,
    textareaRef,
  });
  const {
    handleMarkAllNotificationsRead,
    handleNotificationAction,
    handleNotificationActionStatus,
    notificationPanelOpen,
    notificationToast,
    notificationView,
    notifications,
    notificationsLoading,
    pendingNotificationCount,
    setNotificationPanelOpen,
    setNotificationView,
    unreadNotificationCount,
  } = useNotificationCenter({
    apiOptions,
    downloadGeneratedFile: (file) => downloadGeneratedFile(serverUrl, token, file),
    selectSession,
    serverUrl,
    sessions,
    setActiveWorkspaceId,
    setError,
    setSettingsInitialAdminTab,
    setShowSettings,
    setUtilityPanel,
    token,
  });
  const {
    availableUpdate,
    clientVersion,
    downloadedUpdatePath,
    setUpdateDialogOpen,
    setUpdateStep,
    startClientUpdateDownload,
    updateDialogOpen,
    updateError,
    updateProgress,
    updateStep,
  } = useClientUpdate({ serverUrl, token });
  const {
    auxiliaryPanelMaxWidth,
    auxiliaryPanelRef,
    auxiliaryPanelResizing,
    auxiliaryPanelWidth,
    handleAuxiliaryPanelResizeStart,
    handleSidebarResizeStart,
    handleWorkspaceFilePreviewClose,
    handleWorkspaceFilePreviewOpen,
    handleWorkspacePanelResizeStart,
    sidebarRef,
    sidebarResizing,
    sidebarWidth,
    workspacePanelMaxWidth,
    workspacePanelRef,
    workspacePanelResizing,
    workspacePanelWidth,
  } = useAppShellPanels();
  useAppShellPointerDismiss({
    composerRef,
    modelMenuOpen,
    modelSelectRef,
    notificationButtonRef,
    notificationPanelOpen,
    notificationPanelRef,
    setModelMenuOpen,
    setNotificationPanelOpen,
    setSkillPanelVisible,
    setSlashCommand,
    skillPanelVisible,
  });
  const {
    commitRename,
    deleteConfirmSessionId,
    handleArchiveSession,
    handleDeleteSession,
    handleMoveSession,
    handlePinSession,
    handleRenameSession,
    moveSessionId,
    openSessionMenu,
    renameInput,
    setDeleteConfirmSessionId,
    setMoveSessionId,
    setRenameInput,
  } = useChatSessionManagement({
    activeSessionId,
    activeTabId,
    activeWorkspaceId,
    apiOptions,
    clearAuth,
    selectSession,
    sessions,
    setActionNotice,
    setActiveSessionId,
    setActiveTabId,
    setContextMenu,
    setError,
    setMessagesBySession,
    setSessions,
    setSplitPaneSessionIds,
    setTabs,
    sidebarRenameInputRef,
    tabs,
    titleInputRef,
    workspaces,
  });

  function toggleWebSearch() {
    setWebSearchEnabled((current) => {
      const next = !current;
      writeWebSearchPreference(next);
      return next;
    });
  }

  const activeSessionIsSending = activeSessionId ? Boolean(sendingSessions[activeSessionId]) : false;
  useChatGlobalShortcuts({
    activeSessionId,
    activeSessionIsSending,
    cancelSessionSend,
    setNotificationPanelOpen,
    onOpenSearch: () => setShowSearch(true),
    onNewSession: () => void handleCreateSession(),
  });
  const activeWorkspace = workspaces.find((item) => item.id === activeWorkspaceId);
  const modelOptions = useMemo(() => {
    return llmProviders
      .filter((provider) => provider.configured)
      .map(toModelOption)
      .sort((a, b) => Number(b.isDefault) - Number(a.isDefault) || a.label.localeCompare(b.label, "zh-CN"));
  }, [llmProviders]);
  const selectedModelOption = modelOptions.find((option) => option.key === selectedModelKey) ?? modelOptions.find((option) => option.isDefault) ?? modelOptions[0] ?? null;
  const {
    copiedMessageId,
    deleteLastMessageTarget,
    deleteMessageTarget,
    deletedMessageUndo,
    editingDraft,
    editingMessageId,
    handleActivateVersion,
    handleCopyMessage,
    handleDeleteMessageContext,
    handleExportConversation,
    handleSetBinaryFeedback,
    handleSubmitEditedMessage,
    handleSubmitFeedback,
    handleSubmitGBrainThinkReview,
    handleUndoDeleteMessages,
    messageActionBusyId,
    requestDeleteMessageContext,
    setDeleteConfirmMessageTarget,
    setDeleteLastMessageTarget,
    setDeleteMessageTarget,
    setEditingDraft,
    setEditingMessageId,
    setMessageActionBusyId,
    startEditingMessage,
  } = useChatMessageActions({
    activeWorkspaceId,
    apiOptions,
    clearAuth,
    clearSourcePreview: () => {
      setSourcePreview(null);
      setUtilityPanel((value) => value === "source" ? null : value);
    },
    messagesBySession,
    mode,
    selectedModelOption,
    selectedPromptContent: selectedPrompt.content,
    setActionNotice,
    setError,
    setMessagesBySession,
    setSessions,
    sourcePreviewSessionId: sourcePreview?.sessionId,
    thinkingEnabled,
    webSearchEnabled,
  });
  const {
    handleCopyEditableEmailDraft,
    handleCopyGeneratedEmailBody,
    handleDownloadEditableEmailDraft,
    handleOpenEditableEmailDraft,
    handleOpenGeneratedEmailClient,
  } = useGeneratedEmailDraftActions(copyText);
  const {
    clearTextTransformResult,
    handleApplyTextTransformResult,
    handleCopyTextTransformResult,
    handleTransformMessage,
    textTransformResult,
  } = useTextTransformActions({
    apiOptions,
    clearAuth,
    copyText,
    selectedModelOption,
    setActionNotice,
    setDraft,
    setError,
    setMessageActionBusyId,
    temperature,
    textareaRef,
    thinkingEnabled,
  });
  const {
    handleRegenerateMessage,
    openRegenerateDialog,
    regenerateModelKey,
    regenerateModelOption,
    regenerateTarget,
    setRegenerateModelKey,
    setRegenerateTarget,
  } = useChatRegenerate({
    activeWorkspaceId,
    apiOptions,
    clearAuth,
    mode,
    modelOptions,
    selectedModelOption,
    selectedPromptContent: selectedPrompt.content,
    setError,
    setMessageActionBusyId,
    setMessagesBySession,
    setSessions,
    thinkingEnabled,
    typeAssistantReply,
    webSearchEnabled,
  });
  const {
    attachmentDragTargetPane,
    authorizeLocalPrivateAttachments,
    fileInputRef,
    handleAttachmentDragEnter,
    handleAttachmentDragLeave,
    handleAttachmentDragOver,
    handleAttachmentDrop,
    handleChoosePrivateWorkspaceFiles,
    handleComposerPaste,
    handleReferenceWorkspaceFile,
    handleRemovePendingAttachment,
    handleSelectAttachmentFiles,
    isUploadingAttachments,
    pendingAttachments,
    resolveAttachmentSession,
    revokeAttachmentPreviews,
    setIsUploadingAttachments,
    setPendingAttachments,
    uploadPendingAttachmentForSend,
  } = useChatAttachments({
    activeSessionId,
    activeSplitPane,
    activeWorkspaceId,
    activeWorkspaceKind: activeWorkspace?.workspace_kind,
    apiOptions,
    createSessionFromInput,
    focusComposerRef: textareaRef,
    mode,
    sessions,
    setActiveSplitPane,
    setError,
    activateConversationPane,
  });
  const handleSend = useChatSendOrchestrator({
    activeSessionId,
    activeSessionIsSending,
    activeWorkspaceId,
    apiOptions,
    appendLegacyAssistantResponse,
    clearAuth,
    clearCurrentDraft,
    createSessionFromInput,
    draft,
    finalizeStreamAssistantResponse,
    finishSessionSend,
    mode,
    pendingAttachments,
    registerSendAbortController,
    removeStreamPlaceholder,
    revokeAttachmentPreviews,
    selectedBuiltinCommand,
    selectedModelOption,
    selectedPrompt,
    selectedPromptId,
    selectedSkill,
    sendingSessions,
    sessions,
    setDraft,
    setError,
    setIsUploadingAttachments,
    setMessagesBySession,
    setMode,
    setPendingAttachments,
    quotedMessage,
    setQuotedMessage,
    setSelectedBuiltinCommand,
    setSelectedSkill,
    setSessions,
    setSessionSending,
    setSkillPanelVisible,
    setSlashCommand,
    setTabs,
    temperature,
    thinkingEnabled,
    typeAssistantReply,
    updateStreamPlaceholder,
    uploadPendingAttachmentForSend,
    webSearchEnabled,
  });
  const sessionGroups = useMemo(() => {
    const pinned = sessions.filter((item) => item.is_pinned);
    const recent = sessions.filter((item) => !item.is_pinned);
    const timeGroups = groupSessionsByTime(recent);
    return [
      ...(pinned.length ? [{ key: "pinned", label: null as string | null, items: pinned }] : []),
      ...timeGroups,
    ];
  }, [sessions]);

  const handleKeyDown = useChatComposerShortcuts({
    handleSend,
    insertSlashCandidate,
    setSkillPanelIndex,
    setSkillPanelVisible,
    setSlashCommand,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
  });

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [scrollRef.current, activeSplitPane, splitPaneSessionIds]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Follow bottom only if user was already near bottom BEFORE this update
    if (isNearBottomRef.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    }
  }, [activeMessages]);

  useEffect(() => {
    if (utilityPanel === "source" && sourcePreview?.sessionId != null && sourcePreview.sessionId !== activeSessionId) {
      setSourcePreview(null);
      setUtilityPanel(null);
    }
  }, [activeSessionId, sourcePreview?.sessionId, utilityPanel]);

  useEffect(() => {
    setTabs((current) => {
      if (!current.some((tab) => tab.id === "scratch")) return current;
      return current.filter((tab) => tab.id !== "scratch");
    });
    if (activeTabId === "scratch") {
      setActiveTabId("");
      setActiveSessionId(null);
    }
  }, [activeTabId, setActiveSessionId, setActiveTabId, setTabs]);

  useEffect(() => {
    let mounted = true;
    setIsLoading(true);
    setError(null);
    setSessions([]);
    setActiveSessionId(null);
    if (!activeWorkspaceId) {
      setIsLoading(false);
      return;
    }
    listChatSessions(apiOptions, activeWorkspaceId)
      .then((loadedSessions) => {
        if (!mounted) return;
        setSessions(loadedSessions);
        setError(null);
      })
      .catch((loadError: unknown) => {
        if (!mounted) return;
        if (loadError instanceof ApiError && loadError.status === 401) {
          clearAuth();
          window.location.hash = "#/login";
          return;
        }
        setError("无法加载会话列表，请确认后端正在运行。");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [activeWorkspaceId, apiOptions, clearAuth, setActiveSessionId, setError, setIsLoading, setSessions]);

  useEffect(() => {
    let mounted = true;
    setModelsLoading(true);
    setModelConfigError("");
    getLLMHealth(apiOptions)
      .then((health) => {
        if (!mounted) return;
        setLlmProviders(health.providers);
      })
      .catch(() => {
        if (!mounted) return;
        setLlmProviders([]);
        setModelConfigError("无法读取模型配置");
      })
      .finally(() => {
        if (mounted) setModelsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  useEffect(() => {
    if (modelOptions.length === 0) {
      setSelectedModelKey(null);
      return;
    }
    if (selectedModelKey && modelOptions.some((option) => option.key === selectedModelKey)) return;
    setSelectedModelKey((modelOptions.find((option) => option.isDefault) ?? modelOptions[0]).key);
  }, [modelOptions, selectedModelKey]);

  useEffect(() => {
    let mounted = true;
    listSkills(apiOptions)
      .then((items) => {
        if (mounted) setSkills(items);
      })
      .catch(() => {
        if (mounted) setSkills([]);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  useEffect(() => {
    if (!activeSessionId || messagesBySession[activeSessionId]) return;
    let mounted = true;
    setIsLoading(true);
    setError(null);
    listChatMessages(apiOptions, activeSessionId)
      .then((response) => {
        if (!mounted) return;
        setMessagesBySession((current) => ({ ...current, [activeSessionId]: response.items }));
        setError(null);
      })
      .catch((loadError: unknown) => {
        if (!mounted) return;
        if (loadError instanceof ApiError && loadError.status === 401) {
          clearAuth();
          window.location.hash = "#/login";
          return;
        }
        setError("无法读取消息历史，请稍后重试。");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [activeSessionId, apiOptions, clearAuth, messagesBySession, setError, setIsLoading, setMessagesBySession]);

  useEffect(() => {
    if (!showSearch || !searchTerm.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      searchChatSessions(apiOptions, searchTerm, activeWorkspaceId)
        .then(setSearchResults)
        .catch(() => setSearchResults([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [activeWorkspaceId, apiOptions, searchTerm, showSearch]);

  function selectSession(session: ChatSessionResponse, openInNewTab = false) {
    setShowScratchPad(false);
    setActiveSessionId(session.id);
    if (sideBySideOpen) {
      setSplitPaneSessionIds((current) => ({ ...current, [activeSplitPane]: session.id }));
    }
    const tabId = `chat-${session.id}`;
    setTabs((current) => {
      const existing = current.find((tab) => tab.id === tabId);
      if (existing) return current;
      const nextTab = {
        id: tabId,
        sessionId: session.id,
        workspaceId: session.workspace_id,
        title: session.title,
      };
      if (openInNewTab || !activeTabId) return [...current, nextTab];
      if (!current.some((tab) => tab.id === activeTabId)) return [...current, nextTab];
      return current.map((tab) => tab.id === activeTabId ? nextTab : tab);
    });
    setActiveTabId(tabId);
  }

  async function handleArchiveRestored(session: ChatSessionResponse) {
    const workspaceId = session.workspace_id ?? activeWorkspaceId;
    if (!workspaceId) return;
    if (workspaceId !== activeWorkspaceId) {
      setActiveWorkspaceId(workspaceId);
    }
    try {
      const refreshedSessions = await listChatSessions(apiOptions, workspaceId);
      setSessions(refreshedSessions);
      const restoredSession = refreshedSessions.find((item) => item.id === session.id) ?? { ...session, is_archived: false };
      selectSession(restoredSession);
    } catch {
      if (workspaceId === activeWorkspaceId) {
        const restoredSession = { ...session, is_archived: false };
        setSessions((current) => current.some((item) => item.id === session.id) ? current : [restoredSession, ...current]);
        selectSession(restoredSession);
      }
    }
  }

  async function createSessionFromInput(
    content = "新对话",
    openInNewTab = true,
    promptIdForNewSession: string | null = null,
    paneForNewSession: SplitPaneKey = activeSplitPane,
  ) {
    const resolvedPromptId = promptIdForNewSession ?? (!activeSessionId ? pendingPromptId : null);
    const session = await createChatSession(apiOptions, makeSessionTitle(content), activeWorkspaceId);
    setSessions((current) => [session, ...current]);
    setMessagesBySession((current) => ({ ...current, [session.id]: [] }));
    if (resolvedPromptId) {
      if (resolvedPromptId !== defaultPromptId) {
        storePromptSelection(session.id, resolvedPromptId);
      }
      setPendingPromptId(null);
    }
    selectSession(session, openInNewTab);
    if (sideBySideOpen) {
      setSplitPaneSessionIds((current) => ({ ...current, [paneForNewSession]: session.id }));
    }
    return session;
  }

  async function handleCreateSession() {
    setError(null);
    if (!activeWorkspaceId) {
      setError("请先选择或创建一个项目。");
      return;
    }
    try {
      await createSessionFromInput();
    } catch (createError: unknown) {
      if (createError instanceof ApiError && createError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("新建会话失败，请确认后端连接正常。");
    }
  }

  function handleOpenScratch() {
    setShowScratchPad((current) => {
      const next = !current;
      if (next) {
        setUtilityPanel(null);
      }
      return next;
    });
  }

  function handleLogout() {
    clearAuth();
    window.location.hash = "#/login";
  }

  function handleSelectTab(id: string) {
    setShowScratchPad(false);
    setActiveTabId(id);
    const tab = tabs.find((item) => item.id === id);
    if (tab?.sessionId) {
      setActiveSessionId(tab.sessionId);
      if (sideBySideOpen) {
        setSplitPaneSessionIds((current) => ({ ...current, [activeSplitPane]: tab.sessionId ?? null }));
      }
      if (tab.workspaceId && tab.workspaceId !== activeWorkspaceId) {
        setActiveWorkspaceId(tab.workspaceId);
      }
    }
  }

  function handleWorkspaceChanged(workspaceId: number | null) {
    setActiveWorkspaceId(workspaceId);
    const tab = tabs.find((item) => item.id === activeTabId);
    if (tab?.sessionId && tab.workspaceId !== workspaceId) {
      setActiveTabId("");
      setActiveSessionId(null);
    }
  }

  function handleCloseTab(id: string) {
    const tab = tabs.find((item) => item.id === id);
    if (!tab) return;
    const nextTabs = tabs.filter((item) => item.id !== id);
    setTabs(nextTabs);
    if (activeTabId === id) {
      const next = nextTabs[0];
      if (next) handleSelectTab(next.id);
      else {
        setActiveTabId("");
        setActiveSessionId(null);
      }
    }
  }

  function handleSwitchToAgent(_messageId: number) {
    setMode("agent");
  }

  function handleToggleSideBySide() {
    setSideBySideOpen((current) => {
      if (!current) {
        setActiveSplitPane("left");
        setSplitPaneSessionIds((paneIds) => ({
          left: paneIds.left ?? activeSessionId,
          right: paneIds.right === activeSessionId ? null : paneIds.right,
        }));
      }
      return !current;
    });
  }

  function activateConversationPane(pane: SplitPaneKey, sessionId: number | null) {
    setActiveSplitPane(pane);
    if (sessionId) {
      setActiveSessionId(sessionId);
      setActiveTabId(`chat-${sessionId}`);
    } else {
      setActiveSessionId(null);
      setActiveTabId("");
    }
  }

  function handleSelectSkillFromSidePanel(skill: SkillResponse) {
    setSelectedSkill(skill);
    setSelectedBuiltinCommand(null);
    if (mode === "chat" && skill.outputs.length > 0) {
      setMode("agent");
    }
    setUtilityPanel(null);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function handleSaveGeneratedFileToWorkspace(file: GeneratedFileResponse) {
    if (!activeWorkspaceId || !activeWorkspace || activeWorkspace.workspace_kind === "user") {
      throw new Error("当前工作区不支持保存生成文件");
    }
    const result = await saveGeneratedFileToWorkspace(apiOptions, activeWorkspaceId, {
      generated_file_id: file.id,
      conflict_strategy: "keep_both",
    });
    setWorkspaceFilePanelRefreshKey((value) => value + 1);
    setUtilityPanel("workspace");
    setActionNotice(`已保存到 ${result.path}`);
    return { path: result.path };
  }

  const activeSessionTokenTotal = latestSessionTokenTotal(activeSessionId, messagesBySession);

  const conversationPaneController = {
    activeSessionTokenTotal,
    activeSessionId,
    quotedMessage,
    setQuotedMessage,
    activeSplitPane,
    activeWorkspace,
    apiOptions,
    activateConversationPane,
    attachmentDragTargetPane,
    copiedMessageId,
    currentUser,
    draft,
    editingDraft,
    editingMessageId,
    fileInputRef,
    formatClockTime,
    formatSessionDisplayTitle,
    handleActivateVersion,
    handleAttachmentDragEnter,
    handleAttachmentDragLeave,
    handleAttachmentDragOver,
    handleAttachmentDrop,
    handleCancelSend: cancelSessionSend,
    handleChoosePrivateWorkspaceFiles,
    handleComposerPaste,
    handleCopyMessage,
    handleKeyDown,
    handlePinSession,
    handleRemovePendingAttachment,
    handleRenameSession,
    handleSelectAttachmentFiles,
    handleSubmitEditedMessage,
    handleSubmitGBrainThinkReview,
    onCopyGeneratedEmailBody: handleCopyGeneratedEmailBody,
    onEditGeneratedEmailDraft: setEmailDraftEditorFile,
    onOpenGeneratedEmailClient: handleOpenGeneratedEmailClient,
    onSaveGeneratedFileToWorkspace: handleSaveGeneratedFileToWorkspace,
    onTransformMessage: handleTransformMessage,
    onApplyTextTransformResult: handleApplyTextTransformResult,
    onClearTextTransformResult: clearTextTransformResult,
    onCopyTextTransformResult: handleCopyTextTransformResult,
    handleSwitchToAgent,
    handleToggleSideBySide,
    messageActionBusyId,
    messagesBySession,
    mode,
    openRegenerateDialog,
    renameInput,
    renderAvatar,
    requestDeleteMessageContext,
    scrollRef,
    serverUrl,
    sessions,
    sendingSessions,
    setDeleteConfirmSessionId,
    setDraft,
    setEditingDraft,
    setEditingMessageId,
    setRenameInput,
    setSourcePreview,
    setUtilityPanel,
    sideBySideOpen,
    splitPaneSessionIds,
    startEditingMessage,
    titleInputRef,
    token,
    textTransformResult,
    utilityPanel,
    attachmentSourceLabel,
    authorizeLocalPrivateAttachments,
    clearPromptSelection,
    clearSelectedSkillIfMissing,
    composerRef,
    formatAttachmentSize,
    handleSend,
    insertSlashCandidate,
    isLocalPrivatePendingAttachment,
    isUploadingAttachments,
    modelConfigError,
    modelMenuOpen,
    modelOptions,
    modelsLoading,
    modelSelectRef,
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
    setModelMenuOpen,
    setSelectedBuiltinCommand,
    setSelectedModelKey,
    setSelectedSkill,
    setSkillPanelIndex,
    setThinkingEnabled,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
    syncSlashCommand,
    textareaRef,
    temperature,
    setTemperature,
    thinkingEnabled,
    toggleWebSearch,
    webSearchEnabled,
  };

  function renderConversationPane(pane: SplitPaneKey) {
    return <ChatConversationPane controller={{ ...conversationPaneController, pane }} />;
  }
  return (
    <>
      <AppWorkspaceChrome
        controller={{
        UPDATE_DOWNLOAD_DRY_RUN,
        actionNotice,
        activeSessionId,
        activeTabId,
        activeWorkspace,
        activeWorkspaceId,
        apiOptions,
        auxiliaryPanelMaxWidth,
        auxiliaryPanelRef,
        auxiliaryPanelResizing,
        auxiliaryPanelWidth,
        availableUpdate,
        commitRename,
        companyPrompts,
        contextMenu,
        currentUser,
        clientVersion,
        deleteConfirmSessionId,
        deleteLastMessageTarget,
        deleteMessageTarget,
        deletedMessageUndo,
        downloadedUpdatePath,
        error,
        formatNotificationTime,
        formatSessionDisplayTitle,
        formatSidebarTime,
        formatUpdateBytes,
        formatUpdateSpeed,
        getInitials,
        handleArchiveRestored,
        handleAuxiliaryPanelResizeStart,
        handleCloseTab,
        handleCreateSession,
        handleCreateUserPrompt,
        handleDeleteMessageContext,
        handleDeleteSession,
        handleDeleteUserPrompt,
        handleLogout,
        handleMarkAllNotificationsRead,
        handleMoveSession,
        handleNotificationAction,
        handleNotificationActionStatus,
        handleOpenScratch,
        handleReferenceWorkspaceFile,
        handleRegenerateMessage,
        handleSelectPrompt,
        handleSelectSkillFromSidePanel,
        handleSelectTab,
        handleSetBinaryFeedback,
        handleExportConversation,
        handleSidebarResizeStart,
        handleUndoDeleteMessages,
    handleWorkspaceChanged,
    handleWorkspaceFilePreviewClose,
    handleWorkspaceFilePreviewOpen,
        handleWorkspacePanelResizeStart,
        isLoading,
        messageActionBusyId,
        mode,
        modelOptions,
        moveSessionId,
        notificationButtonRef,
        notificationCategoryLabel,
        notificationPanelOpen,
        notificationPanelRef,
        notificationToast,
        notificationView,
        notifications,
        notificationsLoading,
        openSessionMenu,
        pendingNotificationCount,
        regenerateModelKey,
        regenerateModelOption,
        regenerateTarget,
        renderConversationPane,
        renameInput,
        resolveAvatarUrl,
        searchResults,
        searchTerm,
        selectedPromptId,
        selectSession,
        selectedSkill,
        serverUrl,
        sessionGroups,
        sessions,
        setSourcePreview,
        setActiveMode: setMode,
        setContextMenu,
        setDeleteConfirmSessionId,
        setDeleteLastMessageTarget,
        setDeleteMessageTarget,
        setMoveSessionId,
        setNotificationPanelOpen,
        setNotificationView,
        setRegenerateModelKey,
        setRegenerateTarget,
        setRenameInput,
        setSearchTerm,
        setSettingsInitialAdminTab,
        setShowScratchPad,
        setShowSearch,
        setShowSettings,
        setDraft,
        setUpdateDialogOpen,
        setUpdateStep,
        setUtilityPanel,
        settingsInitialAdminTab,
        showScratchPad,
        showSearch,
        showSettings,
        sideBySideOpen,
        skills,
        sidebarRef,
        sidebarRenameInputRef,
        sidebarResizing,
        sidebarWidth,
        splitPaneSessionIds,
        startClientUpdateDownload,
        sourcePreview,
        tabs,
        textareaRef,
        unreadNotificationCount,
        updateDialogOpen,
        updateError,
        updateProgress,
        updateStep,
        userPrompts,
        utilityPanel,
        workspaceFilePanelRefreshKey,
        workspacePanelMaxWidth,
        workspacePanelRef,
        workspacePanelResizing,
        workspacePanelWidth,
        workspaces,
        }}
      />
      {emailDraftEditorFile ? (
        <EmailDraftEditor
          file={emailDraftEditorFile}
          onClose={() => setEmailDraftEditorFile(null)}
          onCopy={handleCopyEditableEmailDraft}
          onDownload={handleDownloadEditableEmailDraft}
          onOpenEmailClient={handleOpenEditableEmailDraft}
        />
      ) : null}
    </>
  );
}
