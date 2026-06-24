import type { KeyboardEvent } from "react";

import { DEFAULT_SHORTCUTS, PREFS_KEY } from "../settings/settingsPreferences";
import { matchesShortcut, mergeShortcuts } from "../settings/shortcutRegistry";
import type { SkillSlashCandidate, SlashCommandMatch } from "./slashCommands";

type UseChatComposerShortcutsOptions = {
  handleSend: () => Promise<void>;
  insertSlashCandidate: (candidate: SkillSlashCandidate) => void;
  setSkillPanelIndex: (updater: (index: number) => number) => void;
  setSkillPanelVisible: (visible: boolean) => void;
  setSlashCommand: (match: SlashCommandMatch | null) => void;
  skillPanelIndex: number;
  skillPanelVisible: boolean;
  slashCandidates: SkillSlashCandidate[];
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

export function useChatComposerShortcuts({
  handleSend,
  insertSlashCandidate,
  setSkillPanelIndex,
  setSkillPanelVisible,
  setSlashCommand,
  skillPanelIndex,
  skillPanelVisible,
  slashCandidates,
}: UseChatComposerShortcutsOptions) {
  return function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    const shortcuts = readShortcuts();
    if (skillPanelVisible) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (slashCandidates.length > 0) setSkillPanelIndex((i) => (i + 1) % slashCandidates.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (slashCandidates.length > 0) setSkillPanelIndex((i) => (i - 1 + slashCandidates.length) % slashCandidates.length);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        if (slashCandidates.length > 0) insertSlashCandidate(slashCandidates[skillPanelIndex]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setSkillPanelVisible(false);
        setSlashCommand(null);
        return;
      }
    }
    if (matchesShortcut(event.nativeEvent, shortcuts.newline)) {
      return;
    }
    if (matchesShortcut(event.nativeEvent, shortcuts.send)) {
      event.preventDefault();
      void handleSend();
    }
  };
}
