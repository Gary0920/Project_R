import type { NotificationResponse } from "../../shared/api/types";
import { parseApiDate } from "../../shared/utils/time";

export function formatNotificationTime(value: string) {
  const date = parseApiDate(value);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 60_000) return "刚刚";
  if (diffMs < 3_600_000) return `${Math.max(1, Math.floor(diffMs / 60_000))}分钟前`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}小时前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function notificationCategoryLabel(category: NotificationResponse["category"]) {
  return {
    system: "系统",
    task: "任务",
    workspace: "项目",
    approval: "审批",
    risk: "风险",
  }[category];
}

export function shouldToastNotification(notification: NotificationResponse) {
  if (notification.category === "risk" && notification.severity === "critical") return true;
  if (notification.category === "task" && (notification.severity === "success" || notification.severity === "warning")) return true;
  return false;
}

export function numericPayloadValue(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function stringPayloadValue(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
}
