import { useEffect, useMemo, useState, type RefObject } from "react";

import type { SkillResponse } from "../../../shared/api/types";
import {
  BUILTIN_SLASH_COMMANDS,
  findSlashCommand,
  scoreBuiltinSlashCommand,
  scoreSkill,
  type BuiltinSlashCommand,
  type SkillSlashCandidate,
  type SlashCommandMatch,
} from "../slashCommands";
export function useSlashCommandSelection({
  draft,
  mode,
  setDraft,
  setMode,
  skills,
  textareaRef,
}: {
  draft: string;
  mode: "chat" | "agent";
  setDraft: (draft: string) => void;
  setMode: (mode: "chat" | "agent") => void;
  skills: SkillResponse[];
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const [skillPanelVisible, setSkillPanelVisible] = useState(false);
  const [skillPanelIndex, setSkillPanelIndex] = useState(0);
  const [slashCommand, setSlashCommand] = useState<SlashCommandMatch | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillResponse | null>(null);
  const [selectedBuiltinCommand, setSelectedBuiltinCommand] = useState<BuiltinSlashCommand | null>(null);
  const skillQuery = slashCommand?.query ?? "";
  const slashCandidates = useMemo<SkillSlashCandidate[]>(() => {
    const builtinCandidates: SkillSlashCandidate[] = BUILTIN_SLASH_COMMANDS
      .map((command) => ({ kind: "command" as const, command, score: scoreBuiltinSlashCommand(command, skillQuery) }))
      .filter((item) => !skillQuery || item.score > 0);
    const skillCandidates: SkillSlashCandidate[] = skills
      .map((skill) => ({ kind: "skill" as const, skill, score: scoreSkill(skill, skillQuery) }))
      .filter((item) => !skillQuery || item.score > 0);
    return [...builtinCandidates, ...skillCandidates]
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        if (a.kind !== b.kind) return a.kind === "command" ? -1 : 1;
        const aName = a.kind === "command" ? a.command.displayName : a.skill.display_name;
        const bName = b.kind === "command" ? b.command.displayName : b.skill.display_name;
        return aName.localeCompare(bName, "zh-CN");
      })
      .slice(0, 8);
  }, [skills, skillQuery]);

  function syncSlashCommand(value: string, caret: number) {
    const command = findSlashCommand(value, caret);
    setSlashCommand(command);
    setSkillPanelVisible(Boolean(command));
    if (!command) setSkillPanelIndex(0);
  }

  function clearSelectedSkillIfMissing(_value: string) {
    // Skill 选择是本次发送的上下文状态，不再依赖输入框里的触发词。
  }

  function insertSkill(skill: SkillResponse) {
    const target = slashCommand ?? findSlashCommand(draft, textareaRef.current?.selectionStart ?? draft.length);
    if (!target) return;
    const before = draft.slice(0, target.start).replace(/[ \t]+$/, "");
    const after = draft.slice(target.end).replace(/^[ \t]+/, "");
    const spacer = before && after ? " " : "";
    const nextDraft = `${before}${spacer}${after}`;
    const nextCaret = before.length + spacer.length;
    setDraft(nextDraft);
    setSelectedSkill(skill);
    setSelectedBuiltinCommand(null);
    setSlashCommand(null);
    setSkillPanelVisible(false);
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
    });
    if (mode === "chat" && skill.outputs.length > 0) {
      setMode("agent");
    }
  }

  function insertBuiltinSlashCommand(command: BuiltinSlashCommand) {
    const target = slashCommand ?? findSlashCommand(draft, textareaRef.current?.selectionStart ?? draft.length);
    if (!target) return;
    const before = draft.slice(0, target.start).replace(/[ \t]+$/, "");
    const after = draft.slice(target.end).replace(/^[ \t]+/, "");
    const spacer = before && after ? " " : "";
    const nextDraft = `${before}${spacer}${after}`;
    const nextCaret = before.length + spacer.length;
    setDraft(nextDraft);
    setSelectedSkill(null);
    setSelectedBuiltinCommand(command);
    setSlashCommand(null);
    setSkillPanelVisible(false);
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
    });
  }

  function insertSlashCandidate(candidate: SkillSlashCandidate) {
    if (candidate.kind === "command") {
      insertBuiltinSlashCommand(candidate.command);
      return;
    }
    insertSkill(candidate.skill);
  }

  useEffect(() => {
    setSkillPanelIndex(0);
  }, [skillQuery]);

  useEffect(() => {
    setSkillPanelIndex((index) => {
      if (slashCandidates.length === 0) return 0;
      return Math.min(index, slashCandidates.length - 1);
    });
  }, [slashCandidates.length]);

  return {
    clearSelectedSkillIfMissing,
    insertSlashCandidate,
    selectedBuiltinCommand,
    selectedSkill,
    setSelectedBuiltinCommand,
    setSelectedSkill,
    setSkillPanelIndex,
    setSkillPanelVisible,
    setSlashCommand,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
    slashCommand,
    syncSlashCommand,
  };
}
