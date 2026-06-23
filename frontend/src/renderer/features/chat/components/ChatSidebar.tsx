import type { MouseEvent, RefObject } from "react";

import { APP_NAME } from "../../../shared/config/app";
import { ProjectRLogo } from "../../../shared/components/ProjectRLogo";
import { createApiOptions } from "../../../shared/api/options";
import {
  AgentIcon,
  ChatIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  LogoutIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  WorkspaceIcon,
} from "../../../shared/icons/LineIcons";
import { WorkspaceSelector } from "../../workspace/components/WorkspaceSelector";
import { SessionListItem } from "./SessionListItem";

export type ChatSidebarProps = {
  sidebarRef: RefObject<HTMLElement | null>;
  sidebarResizing: boolean;
  sidebarCollapsed: boolean;
  sidebarDisplayWidth: number | null | undefined;
  sidebarWidth: number;
  mode: string;
  setMode: (mode: string) => void;
  activeWorkspace: Record<string, any> | null | undefined;
  apiOptions: ReturnType<typeof createApiOptions>;
  currentUser: Record<string, any> | null | undefined;
  canCreateProject: boolean;
  handleWorkspaceChanged: (workspaceId: number | null) => void;
  handleCreateSession: () => void;
  setShowSearch: (value: boolean) => void;
  isLoading: boolean;
  sessions: any[];
  sessionGroups: any[];
  activeSessionId: number | null;
  commitRename: () => void | Promise<void>;
  formatSessionDisplayTitle: (session: any) => string;
  formatSidebarTime: (value: string) => string;
  openSessionMenu: (event: MouseEvent, session: any) => void;
  renameInput: { id: number; value: string; scope: string } | null;
  selectSession: (sessionId: number) => void;
  setRenameInput: (value: { id: number; value: string; scope: string } | null) => void;
  sideBySideOpen: boolean;
  sidebarRenameInputRef: RefObject<HTMLInputElement | null>;
  splitPaneSessionIds: { left: number | null; right: number | null };
  resolveAvatarUrl: (serverUrl: string, avatar?: string | null) => string;
  serverUrl: string;
  getInitials: (name?: string | null) => string;
  setSettingsInitialAdminTab: (value: string | null) => void;
  setShowSettings: (value: boolean) => void;
  handleLogout: () => void;
  toggleSidebarCollapsed: () => void;
  setSidebarCollapsed: (value: boolean) => void;
  handleSidebarResizeStart: (event: MouseEvent<HTMLDivElement>) => void;
};

export function ChatSidebar({
  sidebarRef,
  sidebarResizing,
  sidebarCollapsed,
  sidebarDisplayWidth,
  sidebarWidth,
  mode,
  setMode,
  activeWorkspace,
  apiOptions,
  currentUser,
  canCreateProject,
  handleWorkspaceChanged,
  handleCreateSession,
  setShowSearch,
  isLoading,
  sessions,
  sessionGroups,
  activeSessionId,
  commitRename,
  formatSessionDisplayTitle,
  formatSidebarTime,
  openSessionMenu,
  renameInput,
  selectSession,
  setRenameInput,
  sideBySideOpen,
  sidebarRenameInputRef,
  splitPaneSessionIds,
  resolveAvatarUrl,
  serverUrl,
  getInitials,
  setSettingsInitialAdminTab,
  setShowSettings,
  handleLogout,
  toggleSidebarCollapsed,
  setSidebarCollapsed,
  handleSidebarResizeStart,
}: ChatSidebarProps) {
  const currentAvatarUrl = resolveAvatarUrl(serverUrl, currentUser?.avatar);

  return (
    <aside
      className={`chat-sidebar ${sidebarResizing ? "is-resizing" : ""} ${sidebarCollapsed ? "is-collapsed" : ""}`}
      ref={sidebarRef as RefObject<HTMLElement>}
      style={{ width: sidebarDisplayWidth ?? sidebarWidth }}
    >
      {sidebarCollapsed ? (
        <div className="sidebar-rail" aria-label="收起侧栏导航">
          <div className="sidebar-rail-section sidebar-rail-brand">
            <span className="sidebar-brand-mark" title={APP_NAME}><ProjectRLogo /></span>
            <button
              aria-label="展开侧边栏"
              className="sidebar-rail-button"
              onClick={toggleSidebarCollapsed}
              title="展开侧边栏"
              type="button"
            >
              <ChevronRightIcon />
            </button>
          </div>

          <div className="sidebar-rail-section" aria-label="模式切换">
            <button
              aria-label="切换到 Agent 模式"
              aria-pressed={mode === "agent"}
              className={`sidebar-rail-button ${mode === "agent" ? "is-active" : ""}`}
              onClick={() => setMode("agent")}
              title="Agent"
              type="button"
            >
              <AgentIcon />
            </button>
            <button
              aria-label="切换到 Chat 模式"
              aria-pressed={mode === "chat"}
              className={`sidebar-rail-button ${mode === "chat" ? "is-active" : ""}`}
              onClick={() => setMode("chat")}
              title="Chat"
              type="button"
            >
              <ChatIcon />
            </button>
          </div>

          <div className="sidebar-rail-section" aria-label="工作区">
            <button
              aria-label="切换工作区"
              className="sidebar-rail-button"
              onClick={() => setSidebarCollapsed(false)}
              title={activeWorkspace ? `切换工作区：${activeWorkspace.name}` : "切换工作区"}
              type="button"
            >
              <WorkspaceIcon />
            </button>
          </div>

          <div className="sidebar-rail-section" aria-label="对话">
            <button
              aria-label="新建对话"
              className="sidebar-rail-button"
              onClick={handleCreateSession}
              title="新建对话"
              type="button"
            >
              <PlusIcon />
            </button>
            <button
              aria-label="搜索对话"
              className="sidebar-rail-button"
              onClick={() => setShowSearch(true)}
              title="搜索对话"
              type="button"
            >
              <SearchIcon />
            </button>
            <button
              aria-label="选择对话"
              className={`sidebar-rail-button ${activeSessionId ? "is-active-soft" : ""}`}
              onClick={() => setSidebarCollapsed(false)}
              title="选择对话"
              type="button"
            >
              <ChatIcon />
            </button>
          </div>

          <div className="sidebar-rail-section sidebar-rail-bottom" aria-label="用户">
            <button
              aria-label="设置"
              className="sidebar-rail-avatar-button"
              onClick={() => {
                setSettingsInitialAdminTab(null);
                setShowSettings(true);
              }}
              title="设置"
              type="button"
            >
              <span className={`sidebar-user-avatar ${!currentAvatarUrl && !currentUser?.avatar ? "is-text" : ""}`}>
                {currentAvatarUrl ? (
                  <img src={currentAvatarUrl} alt="avatar" />
                ) : (
                  currentUser?.avatar || getInitials(currentUser?.nickname)
                )}
              </span>
            </button>
            <button
              aria-label="登出"
              className="sidebar-rail-button"
              onClick={handleLogout}
              title="登出"
              type="button"
            >
              <LogoutIcon />
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="sidebar-top">
            <div className="sidebar-brand">
              <span className="sidebar-brand-mark"><ProjectRLogo /></span>
              <span className="sidebar-brand-name">{APP_NAME}</span>
              <div className="sidebar-brand-actions">
                <button
                  aria-label="搜索对话"
                  className="sidebar-search-button sidebar-brand-search-button"
                  onClick={() => setShowSearch(true)}
                  title="搜索对话"
                  type="button"
                >
                  <SearchIcon />
                </button>
                <button
                  aria-label="收起侧边栏"
                  className="sidebar-collapse-button"
                  onClick={toggleSidebarCollapsed}
                  title="收起侧边栏"
                  type="button"
                >
                  <ChevronLeftIcon />
                </button>
              </div>
            </div>

            <div className="mode-switch" data-active={mode} role="tablist" aria-label="模式切换">
              <span className="mode-switch-indicator" aria-hidden="true" />
              <button
                aria-selected={mode === "agent"}
                className={`mode-tab ${mode === "agent" ? "is-active" : ""}`}
                onClick={() => setMode("agent")}
                role="tab"
                title="Agent"
                type="button"
              >
                <AgentIcon />
                <span>Agent</span>
              </button>
              <button
                aria-selected={mode === "chat"}
                className={`mode-tab ${mode === "chat" ? "is-active" : ""}`}
                onClick={() => setMode("chat")}
                role="tab"
                title="Chat"
                type="button"
              >
                <ChatIcon />
                <span>Chat</span>
              </button>
            </div>

            <WorkspaceSelector
              apiOptions={apiOptions}
              canCreateProject={canCreateProject}
              onWorkspaceChanged={handleWorkspaceChanged}
            />

            <button className="new-chat-button" onClick={handleCreateSession} type="button">
              <PlusIcon />
              <span>新建对话</span>
            </button>
          </div>

          <div className="session-list" aria-label="会话列表">
            {isLoading && sessions.length === 0 ? <p className="sidebar-note">正在加载会话...</p> : null}
            {!isLoading && sessions.length === 0 ? <p className="sidebar-note">当前项目暂无会话。</p> : null}

            {sessionGroups.map((group: any) => (
              <div key={group.key}>
                {group.label ? <p className="session-group-label">{group.label}</p> : null}
                {group.items.map((session: any) => (
                  <SessionListItem
                    activeSessionId={activeSessionId}
                    commitRename={commitRename}
                    formatSessionDisplayTitle={formatSessionDisplayTitle}
                    formatSidebarTime={formatSidebarTime}
                    key={session.id}
                    openSessionMenu={openSessionMenu}
                    renameInput={renameInput}
                    session={session}
                    selectSession={selectSession}
                    setRenameInput={setRenameInput}
                    sideBySideOpen={sideBySideOpen}
                    sidebarRenameInputRef={sidebarRenameInputRef}
                    splitPaneSessionIds={splitPaneSessionIds}
                  />
                ))}
              </div>
            ))}
          </div>

          <div className="sidebar-user">
            <span className={`sidebar-user-avatar ${!currentAvatarUrl && !currentUser?.avatar ? "is-text" : ""}`}>
              {currentAvatarUrl ? (
                <img src={currentAvatarUrl} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                currentUser?.avatar || getInitials(currentUser?.nickname)
              )}
            </span>
            <div className="sidebar-user-info">
              <span className="sidebar-user-name">{currentUser?.nickname ?? "未登录"}</span>
              <span className="sidebar-user-role">{currentUser?.role === "admin" ? "管理员" : "员工"}</span>
            </div>
            <div className="sidebar-user-actions">
              <button
                aria-label="设置"
                className="icon-button"
                onClick={() => {
                  setSettingsInitialAdminTab(null);
                  setShowSettings(true);
                }}
                title="设置"
                type="button"
              >
                <SettingsIcon />
              </button>
              <button aria-label="登出" className="icon-button" onClick={handleLogout} title="登出" type="button">
                <LogoutIcon />
              </button>
            </div>
          </div>
          <div
            aria-orientation="vertical"
            className="sidebar-resize-handle"
            onMouseDown={handleSidebarResizeStart}
            role="separator"
          />
        </>
      )}
    </aside>
  );
}
