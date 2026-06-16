import { useEffect, useRef, useState } from "react";
import { useAtom } from "jotai";

import type { ApiClientOptions } from "../../../shared/api/client";
import type { ChatSessionResponse, GeneratedFileResponse, NotificationResponse } from "../../../shared/api/types";
import { parseApiDate } from "../../../shared/utils/time";
import {
  getNotificationCounts,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationView,
  updateNotificationActionStatus,
} from "../api";
import { notificationsAtom, pendingNotificationCountAtom, unreadNotificationCountAtom } from "../state";
import { numericPayloadValue, shouldToastNotification, stringPayloadValue } from "../formatters";

type SettingsAdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type UtilityPanel = "workspace" | "customer-intelligence" | "prompt" | "skills" | "source" | "crm";

type UseNotificationCenterOptions = {
  apiOptions: ApiClientOptions;
  downloadGeneratedFile: (file: Pick<GeneratedFileResponse, "id" | "filename" | "mime_type" | "download_url">) => Promise<void>;
  selectSession: (session: ChatSessionResponse) => void;
  serverUrl: string;
  sessions: ChatSessionResponse[];
  setActiveWorkspaceId: (workspaceId: number) => void;
  setError: (message: string) => void;
  setSettingsInitialAdminTab: (tab: SettingsAdminTab | null) => void;
  setShowSettings: (visible: boolean) => void;
  setUtilityPanel: (panel: UtilityPanel | null) => void;
  token: string | null;
};

export function useNotificationCenter({
  apiOptions,
  downloadGeneratedFile,
  selectSession,
  sessions,
  setActiveWorkspaceId,
  setError,
  setSettingsInitialAdminTab,
  setShowSettings,
  setUtilityPanel,
  token,
}: UseNotificationCenterOptions) {
  const [notifications, setNotifications] = useAtom(notificationsAtom);
  const [unreadNotificationCount, setUnreadNotificationCount] = useAtom(unreadNotificationCountAtom);
  const [pendingNotificationCount, setPendingNotificationCount] = useAtom(pendingNotificationCountAtom);
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false);
  const [notificationView, setNotificationView] = useState<NotificationView>("all");
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationToast, setNotificationToast] = useState<NotificationResponse | null>(null);
  const notificationStartedAtRef = useRef(new Date());
  const notificationInitializedRef = useRef(false);
  const notificationToastIdsRef = useRef<Set<number>>(new Set());
  const notificationToastTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  async function loadNotificationList(view = notificationView) {
    setNotificationsLoading(true);
    try {
      const response = await listNotifications(apiOptions, view);
      setNotifications(response.items);
      setUnreadNotificationCount(response.unread_count);
      setPendingNotificationCount(response.pending_count);
    } catch {
      setNotifications([]);
    } finally {
      setNotificationsLoading(false);
    }
  }

  function showNotificationToast(notification: NotificationResponse) {
    if (!shouldToastNotification(notification) || notificationToastIdsRef.current.has(notification.id)) return;
    notificationToastIdsRef.current.add(notification.id);
    setNotificationToast(notification);
    if (notificationToastTimerRef.current) {
      window.clearTimeout(notificationToastTimerRef.current);
    }
    notificationToastTimerRef.current = window.setTimeout(() => {
      setNotificationToast(null);
    }, 5000);
  }

  async function refreshNotificationCounts({ allowToast = false } = {}) {
    try {
      const previousUnread = unreadNotificationCount;
      const counts = await getNotificationCounts(apiOptions);
      setUnreadNotificationCount(counts.unread_count);
      setPendingNotificationCount(counts.pending_count);
      if (allowToast && notificationInitializedRef.current && counts.unread_count > previousUnread) {
        const response = await listNotifications(apiOptions, "unread", 5);
        const startedAt = notificationStartedAtRef.current.getTime();
        const toastTarget = response.items.find((item) => {
          const createdAt = parseApiDate(item.created_at).getTime();
          return createdAt >= startedAt && shouldToastNotification(item);
        });
        if (toastTarget) showNotificationToast(toastTarget);
      }
      notificationInitializedRef.current = true;
    } catch {
      // Notification polling must not interrupt chat usage.
    }
  }

  async function markNotificationReadAndRefresh(notification: NotificationResponse) {
    if (!notification.is_read) {
      await markNotificationRead(apiOptions, notification.id);
    }
    await refreshNotificationCounts();
    if (notificationPanelOpen) {
      await loadNotificationList(notificationView);
    }
  }

  async function handleMarkAllNotificationsRead() {
    try {
      await markAllNotificationsRead(apiOptions);
      await refreshNotificationCounts();
      await loadNotificationList(notificationView);
    } catch {
      setError("无法将通知全部标记为已读。");
    }
  }

  async function handleNotificationAction(notification: NotificationResponse) {
    try {
      await markNotificationReadAndRefresh(notification);
      const payload = notification.action_payload ?? {};
      if (notification.action_kind === "open_workspace") {
        const workspaceId = numericPayloadValue(payload, "workspace_id");
        if (workspaceId) {
          setActiveWorkspaceId(workspaceId);
          setUtilityPanel("workspace");
          setNotificationPanelOpen(false);
        }
        return;
      }
      if (notification.action_kind === "open_session") {
        const sessionId = numericPayloadValue(payload, "session_id");
        const targetSession = sessionId ? sessions.find((session) => session.id === sessionId) : null;
        if (targetSession) {
          selectSession(targetSession);
          setNotificationPanelOpen(false);
        }
        return;
      }
      if (notification.action_kind === "open_admin_review") {
        setSettingsInitialAdminTab("reviews");
        setShowSettings(true);
        setNotificationPanelOpen(false);
        return;
      }
      if (notification.action_kind === "open_settings") {
        const tab = stringPayloadValue(payload, "tab");
        setSettingsInitialAdminTab(
          tab && ["overview", "users", "reviews", "gbrain", "templates", "updates", "audit"].includes(tab)
            ? (tab as SettingsAdminTab)
            : "overview",
        );
        setShowSettings(true);
        setNotificationPanelOpen(false);
        return;
      }
      if (notification.action_kind === "download_file" || notification.action_kind === "open_skill_run") {
        const fileId = stringPayloadValue(payload, "file_id");
        const downloadUrl = stringPayloadValue(payload, "download_url") ?? (fileId ? `/documents/${fileId}/download` : null);
        if (fileId && downloadUrl) {
          await downloadGeneratedFile({
            id: fileId,
            filename: stringPayloadValue(payload, "filename") ?? "Project_R文件",
            mime_type: "application/octet-stream",
            download_url: downloadUrl,
          });
          setNotificationPanelOpen(false);
        }
      }
    } catch {
      setError("通知操作失败，请稍后重试。");
    }
  }

  async function handleNotificationActionStatus(notification: NotificationResponse, status: "done" | "dismissed") {
    try {
      await updateNotificationActionStatus(apiOptions, notification.id, status);
      await loadNotificationList(notificationView);
      await refreshNotificationCounts();
    } catch {
      setError(status === "done" ? "无法完成该待办通知。" : "无法忽略该待办通知。");
    }
  }

  useEffect(() => {
    return () => {
      if (notificationToastTimerRef.current) {
        window.clearTimeout(notificationToastTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    void refreshNotificationCounts();
    const timer = window.setInterval(() => {
      void refreshNotificationCounts({ allowToast: true });
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [apiOptions, token, unreadNotificationCount]);

  useEffect(() => {
    if (!notificationPanelOpen || !token) return;
    void loadNotificationList(notificationView);
  }, [notificationPanelOpen, notificationView, token]);

  return {
    handleMarkAllNotificationsRead,
    handleNotificationAction,
    handleNotificationActionStatus,
    loadNotificationList,
    notificationPanelOpen,
    notificationToast,
    notificationView,
    notifications,
    notificationsLoading,
    pendingNotificationCount,
    refreshNotificationCounts,
    setNotificationPanelOpen,
    setNotificationToast,
    setNotificationView,
    unreadNotificationCount,
  };
}
