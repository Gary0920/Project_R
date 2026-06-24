import { useEffect, type MouseEvent } from "react";

import type { SkillResponse } from "../../../shared/api/types";

import { useContextMenu } from "../../../shared/components/ContextMenu";
import { NotificationPopover } from "../../notifications/components/NotificationPopover";
import { PromptPanel } from "../../prompts/components/PromptPanel";
import { SkillsSidePanel } from "./SkillsSidePanel";
import { ScratchPad } from "./ScratchPad";
import { SearchDialog } from "./SearchDialog";
import { ChatSidebar } from "./ChatSidebar";
import { SettingsModal } from "../../settings/components/SettingsModal";
import { TabBar } from "./TabBar";
import { WorkspaceFilePanel } from "../../workspace/components/WorkspaceFilePanel";
import { CrmWorkbenchPanel } from "../../workspace/components/CrmWorkbenchPanel";
import { WindowControls } from "../../../shared/components/WindowControls";
import { renderMessageContent } from "../messageContent";
import { SourcePreviewPanel } from "../../knowledge/components/SourcePreviewPanel";
import {
  BellIcon,
  BrainIcon,
  WorkspaceIcon,
} from "../../../shared/icons/LineIcons";

export type AppWorkspaceChromeProps = {
  controller: Record<string, any>;
};

export function AppWorkspaceChrome({ controller }: AppWorkspaceChromeProps) {
  const {
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
    clientVersion,
    companyPrompts,
    contextMenu,
    currentUser,
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
    gbrainReviewDraft,
    gbrainReviewOriginalQuestion,
    gbrainReviewTarget,
    getInitials,
    handleArchiveRestored,
    handleAuxiliaryPanelResizeStart,
    handleCloseTab,
    handleCreateSession,
    handleCreateUserPrompt,
    handleDeleteMessageContext,
    handleDeleteSession,
    handleDeleteUserPrompt,
    handleUpdateUserPrompt,
    handleLogout,
    handleMarkAllNotificationsRead,
    handleMoveSession,
    handleNotificationAction,
    handleNotificationActionStatus,
    handleNotificationRead,
    handleOpenScratch,
    handleReferenceWorkspaceFile,
    handleRegenerateMessage,
    handleConfirmGBrainThinkReview,
    handleSelectPrompt,
    handleSelectSkillFromSidePanel,
    handleSelectTab,
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
    setActiveMode,
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
    setSidebarCollapsed,
    setGBrainReviewDraft,
    setGBrainReviewTarget,
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
    sidebarCollapsed,
    sidebarDisplayWidth,
    sidebarRenameInputRef,
    sidebarResizing,
    sidebarWidth,
    splitPaneSessionIds,
    startClientUpdateDownload,
    sourcePreview,
    tabs,
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
    commitRename,
    toggleSidebarCollapsed,
  } = controller;
  const setMode = setActiveMode;
  const isCustomerWorkspace = activeWorkspace?.workspace_kind === "customer";

  useEffect(() => {
    if (!isCustomerWorkspace && (utilityPanel === "crm" || utilityPanel === "customer-intelligence")) {
      setUtilityPanel(null);
    }
  }, [isCustomerWorkspace, setUtilityPanel, utilityPanel]);

  function renderUtilityResizeHandle(onMouseDown: (event: MouseEvent<HTMLDivElement>) => void, label: string) {
    return (
      <div
        aria-label={label}
        aria-orientation="vertical"
        className="utility-resize-handle"
        onMouseDown={onMouseDown}
        role="separator"
        title={label}
      />
    );
  }

  function renderSkillsSidePanel() {
    return (
      <SkillsSidePanel
        auxiliaryPanelMaxWidth={auxiliaryPanelMaxWidth}
        auxiliaryPanelRef={auxiliaryPanelRef}
        auxiliaryPanelResizing={auxiliaryPanelResizing}
        auxiliaryPanelWidth={auxiliaryPanelWidth}
        onClose={() => {
          setSourcePreview(null);
          setUtilityPanel(null);
        }}
        onResizeStart={handleAuxiliaryPanelResizeStart}
        onSelectSkill={handleSelectSkillFromSidePanel}
        selectedSkillName={selectedSkill?.name}
        skills={skills as SkillResponse[]}
      />
    );
  }

  function renderSourceSidePanel() {
    const preview = sourcePreview;
    return (
      <aside
        className={`utility-side-pane auxiliary-side-pane source-side-pane ${auxiliaryPanelResizing ? "is-resizing" : ""}`}
        aria-label="引用来源预览"
        ref={auxiliaryPanelRef}
        style={{ flexBasis: auxiliaryPanelWidth, maxWidth: auxiliaryPanelMaxWidth(), width: auxiliaryPanelWidth }}
      >
        {renderUtilityResizeHandle(handleAuxiliaryPanelResizeStart, "调整引用来源面板宽度")}
        <header className="utility-side-header">
          <div>
            <h2>引用来源</h2>
            <p>{preview ? `Source ${preview.index}` : "从正文来源标签打开"}</p>
          </div>
          <button
            className="prompt-panel-close"
            onClick={() => {
              setSourcePreview(null);
              setUtilityPanel(null);
            }}
            type="button"
          >
            ×
          </button>
        </header>
        <SourcePreviewPanel preview={preview} />
      </aside>
    );
  }

  function renderUtilityPanel() {
    if (utilityPanel === "crm") {
      return (
        <CrmWorkbenchPanel
          activeWorkspace={activeWorkspace}
          auxiliaryPanelMaxWidth={auxiliaryPanelMaxWidth()}
          auxiliaryPanelRef={auxiliaryPanelRef}
          auxiliaryPanelResizing={auxiliaryPanelResizing}
          auxiliaryPanelWidth={auxiliaryPanelWidth}
          onClose={() => setUtilityPanel(null)}
          onOpenCustomerIntelligence={() => setUtilityPanel("customer-intelligence")}
          onOpenWorkspaceFiles={() => setUtilityPanel("workspace")}
          resizeHandle={renderUtilityResizeHandle(handleAuxiliaryPanelResizeStart, "调整 CRM 面板宽度")}
        />
      );
    }
    if (utilityPanel === "workspace") {
      if (!activeWorkspace || activeWorkspace.workspace_kind === "user") {
        return null;
      }
      return (
        <aside
          className={`utility-side-pane workspace-files-side-pane ${workspacePanelResizing ? "is-resizing" : ""}`}
          aria-label={activeWorkspace.workspace_kind === "customer" ? "CRM 文件管理面板" : "项目文件常驻面板"}
          ref={workspacePanelRef}
          style={{ flexBasis: workspacePanelWidth, maxWidth: workspacePanelMaxWidth(), width: workspacePanelWidth }}
        >
          {renderUtilityResizeHandle(handleWorkspacePanelResizeStart, activeWorkspace.workspace_kind === "customer" ? "调整 CRM 文件管理面板宽度" : "调整项目文件面板宽度")}
          <header className="utility-side-header">
            <div>
              <h2>{activeWorkspace.workspace_kind === "customer" ? "CRM 文件管理" : "项目文件"}</h2>
              <p>当前工作区常驻视图</p>
            </div>
            <button className="prompt-panel-close" onClick={() => setUtilityPanel(null)} type="button">×</button>
          </header>
          <WorkspaceFilePanel
            apiOptions={apiOptions}
            key={`${activeWorkspaceId ?? "none"}-${workspaceFilePanelRefreshKey ?? 0}`}
            onPreviewOpen={handleWorkspaceFilePreviewOpen}
            onPreviewClose={handleWorkspaceFilePreviewClose}
            workspaceId={activeWorkspaceId}
            workspaceName={activeWorkspace?.name}
            workspaceKind={activeWorkspace?.workspace_kind}
            canIngestKnowledge={Boolean(activeWorkspace.can_rename)}
            defaultPath=""
            onReferenceFile={handleReferenceWorkspaceFile}
          />
        </aside>
      );
    }
    if (utilityPanel === "customer-intelligence") {
      if (!activeWorkspace || activeWorkspace.workspace_kind !== "customer") {
        return null;
      }
      return (
        <WorkspaceFilePanel
          apiOptions={apiOptions}
          workspaceId={activeWorkspaceId}
          workspaceName={activeWorkspace?.name}
          workspaceKind={activeWorkspace?.workspace_kind}
          canIngestKnowledge={Boolean(activeWorkspace.can_rename)}
          standaloneCustomerIntelligence
          onCustomerIntelligenceClose={() => setUtilityPanel(null)}
        />
      );
    }
    if (utilityPanel === "prompt") {
      return (
        <aside
          className={`utility-side-pane auxiliary-side-pane prompt-utility-side-pane ${auxiliaryPanelResizing ? "is-resizing" : ""}`}
          aria-label="提示词面板"
          ref={auxiliaryPanelRef}
          style={{ flexBasis: auxiliaryPanelWidth, maxWidth: auxiliaryPanelMaxWidth(), width: auxiliaryPanelWidth }}
        >
          {renderUtilityResizeHandle(handleAuxiliaryPanelResizeStart, "调整提示词面板宽度")}
          <PromptPanel
            embedded
            selectedPromptId={selectedPromptId}
            companyPrompts={companyPrompts}
            userPrompts={userPrompts}
            onSelect={handleSelectPrompt}
            onCreateUserPrompt={handleCreateUserPrompt}
            onUpdateUserPrompt={handleUpdateUserPrompt}
            onDeleteUserPrompt={handleDeleteUserPrompt}
            onClose={() => setUtilityPanel(null)}
          />
        </aside>
      );
    }
    if (utilityPanel === "skills") {
      return renderSkillsSidePanel();
    }
    if (utilityPanel === "source") {
      return renderSourceSidePanel();
    }
    return null;
  }

  function renderUpdateDialog() {
    if (!updateDialogOpen || !availableUpdate) return null;
    const progressPercent = Math.max(0, Math.min(100, updateProgress?.percent ?? 0));
    const totalBytes = updateProgress?.totalBytes || availableUpdate.size_bytes;
    const receivedBytes = updateProgress?.receivedBytes ?? 0;
    const speed = formatUpdateSpeed(updateProgress?.bytesPerSecond ?? 0);
    const title = updateStep === "ready"
      ? "更新已就绪"
      : updateStep === "installing"
        ? "正在安装更新"
      : updateStep === "downloading"
        ? "正在下载更新"
        : updateStep === "failed"
          ? "更新失败"
          : availableUpdate.is_force_update
            ? "需要更新 Project_R"
            : "发现新版本";
    const description = updateStep === "ready"
      ? `v${availableUpdate.version} 已下载完成，重启应用即可完成更新。`
      : updateStep === "installing"
        ? "校验完成，正在静默安装更新。Project_R 将自动退出，安装器替换当前版本后会自动重启应用。"
      : updateStep === "downloading"
        ? `正在下载 v${availableUpdate.version}...`
        : updateStep === "failed"
          ? updateError || "自动更新失败，请联系管理员获取最新版安装包。"
          : `v${availableUpdate.version} 已发布，请确认后下载更新。`;

    return (
      <div className="update-dialog-backdrop" onClick={() => {
        if (!availableUpdate.is_force_update && updateStep !== "downloading" && updateStep !== "installing") setUpdateDialogOpen(false);
      }}>
        <section className="update-dialog" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
          <header className="update-dialog-header">
            <div>
              <h2>{title}</h2>
              <p>{description}</p>
            </div>
            {UPDATE_DOWNLOAD_DRY_RUN ? <span className="update-dry-run">dry-run</span> : null}
          </header>

          {updateStep === "available" || updateStep === "ready" ? (
            <>
              <div className="update-version-meta">
                <span>本机版本 v{clientVersion || "未知"}</span>
                <span>发布版本 v{availableUpdate.version}</span>
              </div>
              <div className="update-release-notes">
                {renderMessageContent(availableUpdate.release_notes || "本次更新未填写更新日志。")}
              </div>
            </>
          ) : null}

          {updateStep === "downloading" || updateStep === "installing" ? (
            <div className="update-download-panel">
              <div className="update-progress-track">
                <span style={{ width: `${progressPercent}%` }} />
              </div>
              <div className="update-progress-meta">
                <span>{updateStep === "installing" ? "安装中" : `${formatUpdateBytes(receivedBytes)} / ${formatUpdateBytes(totalBytes)}`}</span>
                <span>{updateStep === "installing" ? "安装完成后自动重启" : speed || "校验中"}</span>
              </div>
            </div>
          ) : null}

          {updateStep === "failed" ? (
            <div className="update-failure-message">自动更新失败，请联系管理员获取最新版安装包。</div>
          ) : null}

          <footer className="update-dialog-actions">
            {updateStep === "available" && availableUpdate.is_force_update ? (
              <button className="btn-secondary" onClick={() => void window.projectR?.window?.close()} type="button">退出软件</button>
            ) : null}
            {updateStep === "available" && !availableUpdate.is_force_update ? (
              <button className="btn-secondary" onClick={() => setUpdateDialogOpen(false)} type="button">稍后</button>
            ) : null}
            {updateStep === "available" ? (
              <button className="btn-primary" onClick={() => void startClientUpdateDownload()} type="button">下载并安装</button>
            ) : null}
            {updateStep === "failed" && availableUpdate.is_force_update ? (
              <button className="btn-primary" onClick={() => void window.projectR?.window?.close()} type="button">退出软件</button>
            ) : null}
            {updateStep === "failed" && !availableUpdate.is_force_update ? (
              <button className="btn-primary" onClick={() => setUpdateDialogOpen(false)} type="button">知道了</button>
            ) : null}
          </footer>
        </section>
      </div>
    );
  }

  function gbrainReviewIssueSummary() {
    const think = gbrainReviewTarget?.context_trace?.gbrain_think as any;
    const gaps = Array.isArray(think?.gaps) ? think.gaps.filter(Boolean) : [];
    const conflicts = Array.isArray(think?.conflicts) ? think.conflicts.filter(Boolean) : [];
    const warnings = Array.isArray(think?.warnings) ? think.warnings.filter(Boolean) : [];
    const issue = gaps[0] || conflicts[0] || warnings[0] || "本轮回答发现需要管理员复核的知识信号。";
    if (gaps.length && conflicts.length) return `知识缺口与冲突：${issue}`;
    if (gaps.length) return `知识缺口：${issue}`;
    if (conflicts.length) return `知识冲突：${issue}`;
    return `风险提示：${issue}`;
  }

  function updateGBrainReviewDraft(field: "businessContext" | "expectedKnowledge" | "sourceHint", value: string) {
    setGBrainReviewDraft((current: any) => ({ ...current, [field]: value }));
  }

  function closeGBrainReviewDialog() {
    setGBrainReviewTarget(null);
    setGBrainReviewDraft({ businessContext: "", expectedKnowledge: "", sourceHint: "" });
  }

  function renderGBrainReviewDialog() {
    if (!gbrainReviewTarget) return null;
    const canSubmit = Boolean(gbrainReviewDraft.businessContext.trim() && gbrainReviewDraft.expectedKnowledge.trim());
    return (
      <div className="confirm-overlay" onClick={closeGBrainReviewDialog}>
        <div className="confirm-card message-operation-card gbrain-review-submit-card" onClick={(event) => event.stopPropagation()}>
          <h3>提交知识缺口反馈</h3>
          <p>请先补充业务背景，管理员会根据这些信息判断是否需要补充公司知识或修正资料。</p>
          <div className="gbrain-review-summary">
            <strong>{gbrainReviewIssueSummary()}</strong>
            {gbrainReviewOriginalQuestion ? <span>原问题：{gbrainReviewOriginalQuestion}</span> : null}
          </div>
          <label className="message-operation-field">
            <span>业务场景 / 问题背景 *</span>
            <textarea
              onChange={(event) => updateGBrainReviewDraft("businessContext", event.target.value)}
              placeholder="例如：我正在确认员工请假流程，需要知道年假/病假审批规则。"
              value={gbrainReviewDraft.businessContext}
            />
          </label>
          <label className="message-operation-field">
            <span>期望补充的知识 *</span>
            <textarea
              onChange={(event) => updateGBrainReviewDraft("expectedKnowledge", event.target.value)}
              placeholder="例如：希望补充请假类型、审批人、提前申请时限和需要提交的材料。"
              value={gbrainReviewDraft.expectedKnowledge}
            />
          </label>
          <label className="message-operation-field">
            <span>可参考来源</span>
            <textarea
              onChange={(event) => updateGBrainReviewDraft("sourceHint", event.target.value)}
              placeholder="可选：制度文件名、截图来源、负责人、文件夹位置或其他线索。"
              value={gbrainReviewDraft.sourceHint}
            />
          </label>
          <div className="confirm-actions">
            <button className="btn-secondary" onClick={closeGBrainReviewDialog} type="button">取消</button>
            <button
              className="btn-primary"
              disabled={!canSubmit || messageActionBusyId === gbrainReviewTarget.id}
              onClick={() => void handleConfirmGBrainThinkReview()}
              type="button"
            >
              {messageActionBusyId === gbrainReviewTarget.id ? "提交中" : "提交管理员复核"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const activeTab = (tabs as any[]).find((item: any) => item.id === activeTabId);

  return (
    <div className="shell">
      <ChatSidebar
        sidebarRef={sidebarRef}
        sidebarResizing={sidebarResizing}
        sidebarCollapsed={sidebarCollapsed}
        sidebarDisplayWidth={sidebarDisplayWidth}
        sidebarWidth={sidebarWidth}
        mode={mode}
        setMode={setMode}
        activeWorkspace={activeWorkspace}
        apiOptions={apiOptions}
        currentUser={currentUser}
        canCreateProject={currentUser?.role === "admin"}
        handleWorkspaceChanged={handleWorkspaceChanged}
        handleCreateSession={handleCreateSession}
        setShowSearch={setShowSearch}
        isLoading={isLoading}
        sessions={sessions}
        sessionGroups={sessionGroups}
        activeSessionId={activeSessionId}
        commitRename={commitRename}
        formatSessionDisplayTitle={formatSessionDisplayTitle}
        formatSidebarTime={formatSidebarTime}
        openSessionMenu={openSessionMenu}
        renameInput={renameInput}
        selectSession={selectSession}
        setRenameInput={setRenameInput}
        sideBySideOpen={sideBySideOpen}
        sidebarRenameInputRef={sidebarRenameInputRef}
        splitPaneSessionIds={splitPaneSessionIds}
        resolveAvatarUrl={resolveAvatarUrl}
        serverUrl={serverUrl}
        getInitials={getInitials}
        setSettingsInitialAdminTab={setSettingsInitialAdminTab}
        setShowSettings={setShowSettings}
        handleLogout={handleLogout}
        toggleSidebarCollapsed={toggleSidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
        handleSidebarResizeStart={handleSidebarResizeStart}
      />

      {notificationPanelOpen ? (
        <NotificationPopover
          activeWorkspace={activeWorkspace}
          activeWorkspaceId={activeWorkspaceId}
          availableUpdate={availableUpdate}
          downloadedUpdatePath={downloadedUpdatePath}
          formatNotificationTime={formatNotificationTime}
          handleMarkAllNotificationsRead={handleMarkAllNotificationsRead}
          handleNotificationAction={handleNotificationAction}
          handleNotificationActionStatus={handleNotificationActionStatus}
          handleNotificationRead={handleNotificationRead}
          notificationCategoryLabel={notificationCategoryLabel}
          notificationPanelRef={notificationPanelRef}
          notificationView={notificationView}
          notifications={notifications}
          notificationsLoading={notificationsLoading}
          pendingNotificationCount={pendingNotificationCount}
          setNotificationPanelOpen={setNotificationPanelOpen}
          setNotificationView={setNotificationView}
          setUpdateDialogOpen={setUpdateDialogOpen}
          setUpdateStep={setUpdateStep}
          unreadNotificationCount={unreadNotificationCount}
          updateProgress={updateProgress}
          updateStep={updateStep}
        />
      ) : null}

      <section className="chat-main">
        <TabBar
          tabs={tabs}
          workspaces={workspaces}
          activeTabId={activeTabId}
          scratchOpen={showScratchPad}
          leadingSlot={
            isCustomerWorkspace ? (
              <nav className="workbench-business-nav" aria-label="业务导航">
                <button
                  className={`business-tool-button ${utilityPanel === "crm" || utilityPanel === "customer-intelligence" ? "is-active" : ""}`}
                  onClick={() => setUtilityPanel((value: string | null) => value === "crm" ? null : "crm")}
                  type="button"
                >
                  <BrainIcon />
                  <span>CRM</span>
                </button>
              </nav>
            ) : null
          }
          trailingSlot={
            <>
              <button
                aria-expanded={notificationPanelOpen}
                className={`icon-button notification-button ${unreadNotificationCount > 0 ? "has-unread" : ""}`}
                onClick={() => setNotificationPanelOpen((value: boolean) => !value)}
                ref={notificationButtonRef}
                title="通知中心"
                type="button"
              >
                <BellIcon />
                {unreadNotificationCount > 0 ? (
                  <span className="notification-badge">{unreadNotificationCount > 99 ? "99+" : unreadNotificationCount}</span>
                ) : null}
              </button>
              <WindowControls />
            </>
          }
          onSelectTab={handleSelectTab}
          onCloseTab={handleCloseTab}
          onAddChat={handleCreateSession}
          onOpenScratch={handleOpenScratch}
        />
        {error ? <p className="chat-error">{error}</p> : null}
        {actionNotice ? <p className="chat-notice">{actionNotice}</p> : null}
        {deletedMessageUndo ? (
          <div className="notification-toast message-undo-toast">
            <div>
              <div className="notification-toast-title">已删除当前问答</div>
              <div className="notification-toast-body">上下文已同步清理，可在数秒内撤回。</div>
            </div>
            <button onClick={() => void handleUndoDeleteMessages()} type="button">撤回删除</button>
          </div>
        ) : null}
        {notificationToast ? (
          <div
            className={`notification-toast notification-event-toast is-${notificationToast.severity}`}
            onClick={() => void handleNotificationAction(notificationToast)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                void handleNotificationAction(notificationToast);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <div className="notification-toast-title">{notificationToast.title}</div>
            <div className="notification-toast-body">{notificationToast.content}</div>
          </div>
        ) : null}

        {showScratchPad ? (
          <div className="scratch-pad-workspace">
            <ScratchPad
              workspaceId={activeWorkspaceId}
              workspaceName={activeWorkspace?.name}
              userId={currentUser?.user_id}
              onClose={() => setShowScratchPad(false)}
            />
          </div>
        ) : (
          <div className={`chat-workbench ${sideBySideOpen ? "is-split" : ""} ${utilityPanel && utilityPanel !== "customer-intelligence" ? "has-files-pane" : ""}`}>
            {renderConversationPane("left")}
            {sideBySideOpen ? renderConversationPane("right") : null}
            {renderUtilityPanel()}
          </div>
        )}
      </section>

      {useContextMenu(contextMenu, setContextMenu)}
      {moveSessionId !== null ? (
        <div className="confirm-overlay" onClick={() => setMoveSessionId(null)}>
          <div className="move-project-card" onClick={(event) => event.stopPropagation()}>
            <header className="move-project-header">
              <div>
                <h3>迁移项目</h3>
                <p>选择一个目标项目，当前会话会从项目列表中移出。</p>
              </div>
              <button className="prompt-panel-close" onClick={() => setMoveSessionId(null)} type="button">×</button>
            </header>
            <div className="move-project-list">
              {workspaces
                .filter((workspace: any) => workspace.id !== sessions.find((session: any) => session.id === moveSessionId)?.workspace_id)
                .map((workspace: any) => (
                  <button
                    className="move-project-item"
                    key={workspace.id}
                    onClick={() => void handleMoveSession(moveSessionId, workspace.id)}
                    type="button"
                  >
                    <WorkspaceIcon />
                    <span>{workspace.name}</span>
                    <small>{workspace.member_count} 人</small>
                  </button>
                ))}
            </div>
          </div>
        </div>
      ) : null}
      {showSearch ? (
        <SearchDialog
          sessions={sessions}
          results={searchTerm.trim() ? searchResults : undefined}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          onSelect={(id) => {
            const session = [...sessions, ...searchResults].find((item: any) => item.id === id);
            if (session) selectSession(session);
          }}
          onClose={() => setShowSearch(false)}
        />
      ) : null}

      {regenerateTarget !== null ? (
        <div className="confirm-overlay" onClick={() => setRegenerateTarget(null)}>
          <div className="confirm-card message-operation-card" onClick={(event) => event.stopPropagation()}>
            <h3>重新生成回答</h3>
            <p>保留当前回答为历史版本，并使用所选模型生成一个新版本。当前回答不会被覆盖。</p>
            <label className="message-operation-field">
              <span>使用模型</span>
              <select
                onChange={(event) => setRegenerateModelKey(event.target.value)}
                value={regenerateModelOption?.key ?? ""}
              >
                {(modelOptions as any[]).map((option: any) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setRegenerateTarget(null)} type="button">取消</button>
              <button
                className="btn-primary"
                disabled={!regenerateModelOption || messageActionBusyId === regenerateTarget.id}
                onClick={() => void handleRegenerateMessage(regenerateTarget)}
                type="button"
              >
                生成新版本
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteMessageTarget !== null ? (
        <div className="confirm-overlay" onClick={() => setDeleteMessageTarget(null)}>
          <div className="confirm-card" onClick={(event) => event.stopPropagation()}>
            <h3>删除消息上下文</h3>
            <p>确定删除此条消息对应的问答吗？这些内容会从当前对话视图和后续 AI 上下文中排除，并可在数秒内撤回。</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteMessageTarget(null)} type="button">取消</button>
              <button
                className="btn-danger"
                onClick={() => {
                  void handleDeleteMessageContext(deleteMessageTarget);
                  setDeleteMessageTarget(null);
                }}
                type="button"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteLastMessageTarget !== null ? (
        <div className="confirm-overlay" onClick={() => setDeleteLastMessageTarget(null)}>
          <div className="confirm-card" onClick={(event) => event.stopPropagation()}>
            <h3>删除最后一条消息</h3>
            <p>这是该对话中的最后一组消息。删除后整个对话会被删除，且无法恢复。</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteLastMessageTarget(null)} type="button">取消</button>
              <button
                className="btn-danger"
                onClick={() => {
                  void handleDeleteSession(deleteLastMessageTarget.session_id);
                  setDeleteLastMessageTarget(null);
                }}
                type="button"
              >
                删除对话
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteConfirmSessionId !== null ? (
        <div className="confirm-overlay" onClick={() => setDeleteConfirmSessionId(null)}>
          <div className="confirm-card" onClick={(event) => event.stopPropagation()}>
            <h3>确认删除</h3>
            <p>确定删除此对话吗？此操作不可恢复。</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirmSessionId(null)} type="button">取消</button>
              <button
                className="btn-danger"
                onClick={() => {
                  void handleDeleteSession(deleteConfirmSessionId);
                  setDeleteConfirmSessionId(null);
                }}
                type="button"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {renderGBrainReviewDialog()}
      {renderUpdateDialog()}
      <SettingsModal
        initialAdminTab={settingsInitialAdminTab ?? undefined}
        initialSection={settingsInitialAdminTab ? "admin" : undefined}
        isOpen={showSettings}
        onArchiveRestored={handleArchiveRestored}
        onClose={() => {
          setShowSettings(false);
          setSettingsInitialAdminTab(null);
        }}
      />
    </div>
  );

}
