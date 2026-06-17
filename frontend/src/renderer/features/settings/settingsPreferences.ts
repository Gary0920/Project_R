import { parseApiDate } from "../../shared/utils/time";

export type PreferenceState = {
  completionSound: boolean;
  autoArchiveDays: string;
  floatingPinBar: boolean;
  theme: "system" | "light" | "dark";
  dingTalkWebhook: string;
  dingTalkToken: string;
  shortcuts: Record<string, string>;
};

export const DEFAULT_SHORTCUTS: Record<string, string> = {
  newChat: "Ctrl + N",
  search: "Ctrl + K",
  settings: "Ctrl + ,",
  send: "Enter",
  newline: "Shift + Enter",
};

export const PREFS_KEY = "project-r:settings-preferences";

export function readPreferences(): PreferenceState {
  try {
    return {
      completionSound: false,
      autoArchiveDays: "disabled",
      floatingPinBar: true,
      theme: "system",
      dingTalkWebhook: "",
      dingTalkToken: "",
      shortcuts: DEFAULT_SHORTCUTS,
      ...JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}"),
    };
  } catch {
    return {
      completionSound: false,
      autoArchiveDays: "disabled",
      floatingPinBar: true,
      theme: "system",
      dingTalkWebhook: "",
      dingTalkToken: "",
      shortcuts: DEFAULT_SHORTCUTS,
    };
  }
}

export function applyTheme(theme: PreferenceState["theme"]) {
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  const resolved = theme === "system" ? (prefersDark ? "dark" : "light") : theme;
  document.documentElement.dataset.theme = resolved;
}

export function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(value: string | number) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parseApiDate(value));
}

export function formatOptionalDate(value?: string | null) {
  if (!value) return "暂无记录";
  const date = parseApiDate(value);
  if (Number.isNaN(date.getTime())) return "暂无记录";
  return formatDate(value);
}

export function resolveServerAssetUrl(serverUrl: string, value?: string | null) {
  if (!value) return "";
  if (value.startsWith("http") || value.startsWith("data:")) return value;
  if (value.startsWith("/")) return `${serverUrl.replace(/\/$/, "")}${value}`;
  return "";
}
