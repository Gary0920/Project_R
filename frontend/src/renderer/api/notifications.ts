import { apiRequest, type ApiClientOptions } from "./client";
import type { NotificationCountsResponse, NotificationsListResponse } from "./types";

export type NotificationView = "all" | "unread" | "pending";

export function listNotifications(
  options: ApiClientOptions,
  view: NotificationView = "all",
  limit = 50,
) {
  const query = new URLSearchParams({ view, limit: String(limit) });
  return apiRequest<NotificationsListResponse>(options, `/notifications?${query.toString()}`);
}

export function getNotificationCounts(options: ApiClientOptions) {
  return apiRequest<NotificationCountsResponse>(options, "/notifications/counts");
}

export function markNotificationRead(options: ApiClientOptions, notificationId: number) {
  return apiRequest<{ ok: boolean }>(options, `/notifications/${notificationId}/read`, {
    method: "POST",
  });
}

export function markAllNotificationsRead(options: ApiClientOptions) {
  return apiRequest<{ ok: boolean }>(options, "/notifications/read-all", {
    method: "POST",
  });
}

export function updateNotificationActionStatus(
  options: ApiClientOptions,
  notificationId: number,
  status: "done" | "dismissed",
) {
  return apiRequest<{ ok: boolean }>(options, `/notifications/${notificationId}/action-status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}
