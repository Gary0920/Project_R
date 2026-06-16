import { useEffect, type RefObject } from "react";

type UseAppShellPointerDismissOptions = {
  composerRef: RefObject<HTMLDivElement | null>;
  modelMenuOpen: boolean;
  modelSelectRef: RefObject<HTMLDivElement | null>;
  notificationButtonRef: RefObject<HTMLButtonElement | null>;
  notificationPanelOpen: boolean;
  notificationPanelRef: RefObject<HTMLDivElement | null>;
  setModelMenuOpen: (open: boolean) => void;
  setNotificationPanelOpen: (open: boolean) => void;
  setSkillPanelVisible: (visible: boolean) => void;
  setSlashCommand: (value: null) => void;
  skillPanelVisible: boolean;
};

export function useAppShellPointerDismiss({
  composerRef,
  modelMenuOpen,
  modelSelectRef,
  notificationButtonRef,
  notificationPanelOpen,
  notificationPanelRef,
  setModelMenuOpen,
  setNotificationPanelOpen,
  setSkillPanelVisible,
  setSlashCommand,
  skillPanelVisible,
}: UseAppShellPointerDismissOptions) {
  useEffect(() => {
    function handlePointerDown(event: globalThis.MouseEvent) {
      const target = event.target;
      const insideComposer = target instanceof Node && Boolean(composerRef.current?.contains(target));
      const insideModelSelect = target instanceof Node && Boolean(modelSelectRef.current?.contains(target));
      const insideNotificationPanel = target instanceof Node && Boolean(notificationPanelRef.current?.contains(target));
      const insideNotificationButton = target instanceof Node && Boolean(notificationButtonRef.current?.contains(target));
      if (modelMenuOpen && !insideModelSelect) {
        setModelMenuOpen(false);
      }
      if (skillPanelVisible && !insideComposer) {
        setSkillPanelVisible(false);
        setSlashCommand(null);
      }
      if (notificationPanelOpen && !insideNotificationPanel && !insideNotificationButton) {
        setNotificationPanelOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [
    composerRef,
    modelMenuOpen,
    modelSelectRef,
    notificationButtonRef,
    notificationPanelOpen,
    notificationPanelRef,
    setModelMenuOpen,
    setNotificationPanelOpen,
    setSkillPanelVisible,
    setSlashCommand,
    skillPanelVisible,
  ]);
}
