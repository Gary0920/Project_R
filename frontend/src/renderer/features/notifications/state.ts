import { atom } from "jotai";

export type Notification = {
  id: number;
  type: string;
  category: "system" | "task" | "workspace" | "approval" | "risk";
  severity: "info" | "success" | "warning" | "critical";
  title: string;
  content: string;
  is_read: boolean;
  action_status: "none" | "pending" | "done" | "dismissed";
  action_kind: "" | "open_session" | "open_workspace" | "open_skill_run" | "download_file" | "open_admin_review" | "open_settings";
  action_payload: Record<string, unknown>;
  event_key: string;
  link: string;
  created_at: string;
  expires_at: string | null;
};

export const notificationsAtom = atom<Notification[]>([]);
export const unreadNotificationCountAtom = atom(0);
export const pendingNotificationCountAtom = atom(0);
