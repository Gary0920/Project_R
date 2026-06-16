import { useEffect } from "react";

type UseChatGlobalShortcutsOptions = {
  activeSessionId: number | null;
  activeSessionIsSending: boolean;
  cancelSessionSend: (sessionId: number | null | undefined) => void;
  setNotificationPanelOpen: (open: boolean) => void;
};

export function useChatGlobalShortcuts({
  activeSessionId,
  activeSessionIsSending,
  cancelSessionSend,
  setNotificationPanelOpen,
}: UseChatGlobalShortcutsOptions) {
  useEffect(() => {
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape") return;
      setNotificationPanelOpen(false);
      if (activeSessionIsSending) {
        event.preventDefault();
        cancelSessionSend(activeSessionId);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [activeSessionId, activeSessionIsSending, cancelSessionSend, setNotificationPanelOpen]);
}
