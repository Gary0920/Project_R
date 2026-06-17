import { useState, type RefObject } from "react";

import type { NotificationView } from "../api";
import type { ClientUpdateInfo, NotificationResponse, WorkspaceResponse } from "../../../shared/api/types";

type ClientUpdateStep = "available" | "downloading" | "installing" | "ready" | "failed";

type UpdateProgress = {
  status?: string;
};

export type NotificationPopoverProps = {
  activeWorkspace?: WorkspaceResponse | null;
  activeWorkspaceId?: number | null;
  availableUpdate?: ClientUpdateInfo | null;
  downloadedUpdatePath?: string;
  formatNotificationTime: (value: string) => string;
  handleMarkAllNotificationsRead: () => void | Promise<void>;
  handleNotificationAction: (notification: NotificationResponse) => void | Promise<void>;
  handleNotificationActionStatus: (notification: NotificationResponse, status: "done" | "dismissed") => void | Promise<void>;
  notificationCategoryLabel: (category: NotificationResponse["category"]) => string;
  notificationPanelRef: RefObject<HTMLDivElement | null>;
  notificationView: NotificationView;
  notifications: NotificationResponse[];
  notificationsLoading: boolean;
  pendingNotificationCount: number;
  setNotificationPanelOpen: (open: boolean) => void;
  setNotificationView: (view: NotificationView) => void;
  setUpdateDialogOpen: (open: boolean) => void;
  setUpdateStep: (step: ClientUpdateStep) => void;
  unreadNotificationCount: number;
  updateProgress?: UpdateProgress | null;
  updateStep: ClientUpdateStep;
};

export function NotificationPopover({
  activeWorkspace,
  activeWorkspaceId,
  availableUpdate,
  downloadedUpdatePath,
  formatNotificationTime,
  handleMarkAllNotificationsRead,
  handleNotificationAction,
  handleNotificationActionStatus,
  notificationCategoryLabel,
  notificationPanelRef,
  notificationView,
  notifications,
  notificationsLoading,
  pendingNotificationCount,
  setNotificationPanelOpen,
  setNotificationView,
  setUpdateDialogOpen,
  setUpdateStep,
  unreadNotificationCount,
  updateProgress,
  updateStep,
}: NotificationPopoverProps) {
  const [notificationScope, setNotificationScope] = useState<"all" | "workspace">("all");
  const tabs: Array<{ id: NotificationView; label: string; badge?: number }> = [
    { id: "all", label: "全部" },
    { id: "unread", label: "未读", badge: unreadNotificationCount },
    { id: "pending", label: "待处理", badge: pendingNotificationCount },
  ];
  const visibleNotifications = notificationScope === "workspace" && activeWorkspaceId
    ? notifications.filter((notification) => Number(notification.action_payload?.workspace_id) === Number(activeWorkspaceId))
    : notifications;
  const visibleUnreadCount = visibleNotifications.filter((notification) => !notification.is_read).length;
  const visiblePendingCount = visibleNotifications.filter((notification) => notification.action_status === "pending").length;

  return (
    <div className="notification-popover" ref={notificationPanelRef} role="dialog" aria-label="通知中心">
      <header className="notification-popover-header">
        <div>
          <h2>通知中心</h2>
          <p>{notificationScope === "workspace" && activeWorkspace ? activeWorkspace.name : "全部工作区与系统通知"}</p>
        </div>
        <button
          className="notification-mark-read"
          disabled={unreadNotificationCount === 0}
          onClick={() => void handleMarkAllNotificationsRead()}
          type="button"
        >
          全部已读
        </button>
      </header>

      <div className="notification-summary" aria-label="通知概览">
        <span>
          <strong>{visibleUnreadCount}</strong>
          <small>当前未读</small>
        </span>
        <span>
          <strong>{visiblePendingCount}</strong>
          <small>待处理</small>
        </span>
        <span>
          <strong>{visibleNotifications.length}</strong>
          <small>当前列表</small>
        </span>
      </div>

      <div className="notification-tabs" role="tablist" aria-label="通知分类">
        {tabs.map((tab) => (
          <button
            aria-selected={notificationView === tab.id}
            className={`notification-tab ${notificationView === tab.id ? "is-active" : ""}`}
            key={tab.id}
            onClick={() => setNotificationView(tab.id)}
            role="tab"
            type="button"
          >
            <span>{tab.label}</span>
            {tab.badge ? <small>{tab.badge > 99 ? "99+" : tab.badge}</small> : null}
          </button>
        ))}
      </div>

      <div className="notification-scope-tabs" aria-label="通知范围">
        <button
          className={notificationScope === "all" ? "is-active" : ""}
          onClick={() => setNotificationScope("all")}
          type="button"
        >
          全部通知
        </button>
        <button
          className={notificationScope === "workspace" ? "is-active" : ""}
          disabled={!activeWorkspaceId}
          onClick={() => setNotificationScope("workspace")}
          type="button"
        >
          当前工作区
        </button>
      </div>

      {availableUpdate ? (
        <button
          className="notification-update-entry"
          onClick={() => {
            setUpdateStep(downloadedUpdatePath ? "ready" : updateProgress?.status === "downloading" ? "downloading" : "available");
            setUpdateDialogOpen(true);
            setNotificationPanelOpen(false);
          }}
          type="button"
        >
          <span>
            <strong>新版本可用</strong>
            <small>Project_R v{availableUpdate.version} · {updateStep === "ready" ? "已下载完成" : "点击查看发布说明"}</small>
          </span>
          <span>{updateStep === "ready" ? "已就绪" : "查看"}</span>
        </button>
      ) : null}

      <div className="notification-list">
        {notificationsLoading ? <div className="notification-empty">正在读取通知...</div> : null}
        {!notificationsLoading && visibleNotifications.length === 0 ? <div className="notification-empty">暂无通知</div> : null}
        {!notificationsLoading
          ? visibleNotifications.map((notification) => {
              const isPending = notification.action_status === "pending";
              const canDismiss = isPending && notification.severity !== "critical";
              return (
                <article
                  className={`notification-item is-${notification.category} is-${notification.severity} ${notification.is_read ? "" : "is-unread"} ${isPending ? "is-pending" : ""}`}
                  key={notification.id}
                >
                  <div
                    className="notification-item-main"
                    onClick={() => void handleNotificationAction(notification)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        void handleNotificationAction(notification);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="notification-item-meta">
                      <div>
                        <span className={`notification-category is-${notification.category}`}>
                          {notificationCategoryLabel(notification.category)}
                        </span>
                        {isPending ? <span className="notification-status">待处理</span> : null}
                      </div>
                      <time>{formatNotificationTime(notification.created_at)}</time>
                    </div>
                    <h3>{notification.title}</h3>
                    <p>{notification.content}</p>
                  </div>

                  {isPending ? (
                    <div className="notification-item-actions">
                      <button
                        className="notification-action-primary"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleNotificationActionStatus(notification, "done");
                        }}
                        type="button"
                      >
                        已处理
                      </button>
                      {canDismiss ? (
                        <button
                          className="notification-action-secondary"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleNotificationActionStatus(notification, "dismissed");
                          }}
                          type="button"
                        >
                          忽略
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })
          : null}
      </div>
    </div>
  );
}
