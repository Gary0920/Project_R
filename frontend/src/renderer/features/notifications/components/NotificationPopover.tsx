import { useEffect, useState, type RefObject } from "react";

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
  handleNotificationRead: (notification: NotificationResponse) => void | Promise<void>;
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
  handleNotificationRead,
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
  const [selectedNotificationId, setSelectedNotificationId] = useState<number | null>(null);
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
  const scopeLabel = notificationScope === "workspace" && activeWorkspace ? activeWorkspace.name : "全部工作区与系统通知";

  useEffect(() => {
    if (selectedNotificationId && !visibleNotifications.some((notification) => notification.id === selectedNotificationId)) {
      setSelectedNotificationId(null);
    }
  }, [selectedNotificationId, visibleNotifications]);

  function handleSelectNotification(notification: NotificationResponse) {
    setSelectedNotificationId(notification.id);
    void handleNotificationRead(notification);
  }

  return (
    <div className="notification-popover" ref={notificationPanelRef} role="dialog" aria-label="通知中心">
      <header className="notification-popover-header">
        <div className="notification-popover-title">
          <h2>通知中心</h2>
          <p>{scopeLabel}</p>
          <div
            className="notification-popover-counts"
            aria-label={`通知统计：${visibleUnreadCount} 条未读，${visiblePendingCount} 项待处理，共 ${visibleNotifications.length} 条`}
          >
            <span className="notification-count-item">
              <strong>{visibleUnreadCount}</strong>
              <small>未读</small>
            </span>
            <span className="notification-count-item">
              <strong>{visiblePendingCount}</strong>
              <small>待处理</small>
            </span>
            <span className="notification-count-item">
              <strong>{visibleNotifications.length}</strong>
              <small>总计</small>
            </span>
          </div>
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

      <div className="notification-toolbar">
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
            全部
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
              const isSelected = selectedNotificationId === notification.id;
              const canDismiss = isPending && notification.severity !== "critical";
              const displayContent = getNotificationDisplayContent(notification);
              const actionLabel = getNotificationActionLabel(notification);
              const actions = (
                <div className="notification-item-actions">
                  {notification.action_kind ? (
                    <button
                      className="notification-action-secondary"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleNotificationAction(notification);
                      }}
                      type="button"
                    >
                      {actionLabel}
                    </button>
                  ) : null}
                  {isPending ? (
                    <>
                      <button
                        className="notification-action-secondary"
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
                    </>
                  ) : null}
                </div>
              );
              return (
                <article
                  className={`notification-item is-${notification.category} is-${notification.severity} ${notification.is_read ? "" : "is-unread"} ${isPending ? "is-pending" : ""} ${isSelected ? "is-selected" : ""}`}
                  key={notification.id}
                  onClick={() => handleSelectNotification(notification)}
                  onDoubleClick={() => void handleNotificationAction(notification)}
                >
                  <div className="notification-item-body">
                    <div className="notification-item-main">
                      <span className="notification-item-indicator" aria-hidden="true" />
                      <div className="notification-item-content">
                        <div className="notification-item-meta">
                          <div>
                            <span className={`notification-category is-${notification.category}`}>
                              {notificationCategoryLabel(notification.category)}
                            </span>
                            {isPending ? <span className="notification-status">待处理</span> : null}
                          </div>
                        </div>
                        <h3>{notification.title}</h3>
                        <p>{displayContent.summary}</p>

                        {displayContent.source ? (
                          <div className="notification-source-meta" aria-label={`来源：${displayContent.source}`}>
                            <span>来源</span>
                            <code>{displayContent.sourceLabel}</code>
                            {displayContent.sourceDetail ? <code>{displayContent.sourceDetail}</code> : null}
                          </div>
                        ) : null}
                      </div>
                    </div>

                    <div className="notification-item-utility">
                      <time>{formatNotificationTime(notification.created_at)}</time>
                      {actions}
                    </div>
                  </div>
                </article>
              );
            })
          : null}
      </div>
    </div>
  );
}

function getNotificationDisplayContent(notification: NotificationResponse) {
  const content = notification.content.trim();
  const sourceMatch = content.match(/(?:^|[。；;\s])来源[:：]\s*(.+)$/);
  const payloadSource = getPayloadString(notification.action_payload, "source")
    ?? getPayloadString(notification.action_payload, "review_source")
    ?? getPayloadString(notification.action_payload, "source_id");
  const source = (sourceMatch?.[1] ?? payloadSource ?? "").trim();
  const summary = sourceMatch ? content.slice(0, sourceMatch.index).trim() : content;
  const messageId = getPayloadString(notification.action_payload, "message_id");
  const sourceDetailFromPayload = messageId ? `message:${messageId}` : null;
  const sourceParts = source.split(/:(?=message:)/);
  return {
    summary: summary || content,
    source,
    sourceLabel: sourceParts[0] || source,
    sourceDetail: sourceParts.length > 1 ? sourceParts.slice(1).join(":") : sourceDetailFromPayload,
  };
}

function getPayloadString(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return null;
}

function getNotificationActionLabel(notification: NotificationResponse) {
  if (notification.action_kind === "download_file") return "下载";
  if (notification.action_kind === "open_settings") return "设置";
  return "打开";
}
