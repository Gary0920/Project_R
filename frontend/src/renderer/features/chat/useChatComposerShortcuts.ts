import type { KeyboardEvent } from "react";

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
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };
}
