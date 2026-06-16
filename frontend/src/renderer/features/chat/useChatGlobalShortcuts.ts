import { useEffect } from "react";

type UseChatGlobalShortcutsOptions = {
  activeSessionId: number | null;
  activeSessionIsSending: boolean;
  cancelSessionSend: (sessionId: number | null | undefined) => void;
  setNotificationPanelOpen: (open: boolean) => void;
  onOpenSearch?: () => void;
  onNewSession?: () => void;
};

const PREFS_KEY = "project-r:settings-preferences";
const DEFAULT_SHORTCUTS: Record<string, string> = {
  newChat: "Ctrl + N",
  search: "Ctrl + K",
  settings: "Ctrl + ,",
  send: "Enter",
  newline: "Shift + Enter",
};

function readShortcuts(): Record<string, string> {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_SHORTCUTS;
    const prefs = JSON.parse(raw);
    return { ...DEFAULT_SHORTCUTS, ...(prefs.shortcuts ?? {}) };
  } catch {
    return DEFAULT_SHORTCUTS;
  }
}

/** 将 "Ctrl + K" 或 "Cmd + K" 格式转为 (ctrlKey, metaKey, key) 判断函数。 */
function parseShortcut(combo: string): (event: globalThis.KeyboardEvent) => boolean {
  const parts = combo.split("+").map((s) => s.trim().toLowerCase());
  const ctrl = parts.includes("ctrl");
  const meta = parts.includes("meta") || parts.includes("cmd");
  const shift = parts.includes("shift");
  const alt = parts.includes("alt");
  // 最后部分是键名
  const keyPart = parts[parts.length - 1];
  return (event) => {
    if (ctrl !== event.ctrlKey) return false;
    if (meta !== event.metaKey) return false;
    if (shift !== event.shiftKey) return false;
    if (alt !== event.altKey) return false;
    return event.key.toLowerCase() === keyPart;
  };
}

export function useChatGlobalShortcuts({
  activeSessionId,
  activeSessionIsSending,
  cancelSessionSend,
  setNotificationPanelOpen,
  onOpenSearch,
  onNewSession,
}: UseChatGlobalShortcutsOptions) {
  useEffect(() => {
    const shortcuts = readShortcuts();
    const matchNewChat = parseShortcut(shortcuts.newChat ?? "Ctrl + N");
    const matchSearch = parseShortcut(shortcuts.search ?? "Ctrl + K");

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      // 输入框/文本区中不拦截全局快捷键（Escape 除外）
      if (event.key !== "Escape") {
        const tag = (event.target as HTMLElement)?.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || (event.target as HTMLElement)?.isContentEditable) {
          return;
        }
      }
      // Escape 总是可用
      if (event.key === "Escape") {
        setNotificationPanelOpen(false);
        if (activeSessionIsSending) {
          event.preventDefault();
          cancelSessionSend(activeSessionId);
        }
        return;
      }

      if (matchNewChat(event) && onNewSession) {
        event.preventDefault();
        onNewSession();
        return;
      }

      if (matchSearch(event) && onOpenSearch) {
        event.preventDefault();
        onOpenSearch();
        return;
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [activeSessionId, activeSessionIsSending, cancelSessionSend, setNotificationPanelOpen, onOpenSearch, onNewSession]);
}
