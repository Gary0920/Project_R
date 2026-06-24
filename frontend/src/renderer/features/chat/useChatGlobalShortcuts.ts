import { useEffect } from "react";

import { DEFAULT_SHORTCUTS, PREFS_KEY } from "../settings/settingsPreferences";
import { matchesShortcut, mergeShortcuts } from "../settings/shortcutRegistry";

type UseChatGlobalShortcutsOptions = {
  activeSessionId: number | null;
  activeSessionIsSending: boolean;
  cancelSessionSend: (sessionId: number | null | undefined) => void;
  setNotificationPanelOpen: (open: boolean) => void;
  onOpenSearch?: () => void;
  onOpenSettings?: () => void;
  onNewSession?: () => void;
};

function readShortcuts(): Record<string, string> {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_SHORTCUTS;
    const prefs = JSON.parse(raw);
    return mergeShortcuts(prefs.shortcuts);
  } catch {
    return DEFAULT_SHORTCUTS;
  }
}

export function useChatGlobalShortcuts({
  activeSessionId,
  activeSessionIsSending,
  cancelSessionSend,
  setNotificationPanelOpen,
  onOpenSearch,
  onOpenSettings,
  onNewSession,
}: UseChatGlobalShortcutsOptions) {
  useEffect(() => {
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      const shortcuts = readShortcuts();
      // 输入框/文本区中不拦截全局快捷键（Escape 除外）
      if (event.key !== "Escape") {
        const tag = (event.target as HTMLElement)?.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || (event.target as HTMLElement)?.isContentEditable) {
          return;
        }
      }
      if (event.key === "Escape") {
        setNotificationPanelOpen(false);
        if (activeSessionIsSending) {
          event.preventDefault();
          cancelSessionSend(activeSessionId);
        }
        return;
      }

      if (matchesShortcut(event, shortcuts.newChat) && onNewSession) {
        event.preventDefault();
        onNewSession();
        return;
      }

      if (matchesShortcut(event, shortcuts.search) && onOpenSearch) {
        event.preventDefault();
        onOpenSearch();
        return;
      }

      if (matchesShortcut(event, shortcuts.settings) && onOpenSettings) {
        event.preventDefault();
        onOpenSettings();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [
    activeSessionId,
    activeSessionIsSending,
    cancelSessionSend,
    setNotificationPanelOpen,
    onOpenSearch,
    onOpenSettings,
    onNewSession,
  ]);
}
