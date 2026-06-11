import type { SkillResponse } from "../../shared/api/types";

export type SlashCommandMatch = {
  start: number;
  end: number;
  query: string;
};

export type BuiltinSlashCommand = {
  kind: "command";
  name: string;
  displayName: string;
  description: string;
  insertText: string;
  scope: string;
  aliases: string[];
};

export type SkillSlashCandidate =
  | { kind: "command"; command: BuiltinSlashCommand; score: number }
  | { kind: "skill"; skill: SkillResponse; score: number };

export const BUILTIN_SLASH_COMMANDS: BuiltinSlashCommand[] = [
  {
    kind: "command",
    name: "query",
    displayName: "查询知识库",
    description: "使用 GBrain 检索公司知识库和当前项目知识库，并返回引用来源。",
    insertText: "/query ",
    scope: "GBrain",
    aliases: ["query", "知识库", "查询", "gbrain", "ask"],
  },
];

export function findSlashCommand(text: string, caret: number): SlashCommandMatch | null {
  const beforeCaret = text.slice(0, caret);
  const match = /(?:^|\n)[ \t]*\/([^\n]*)$/.exec(beforeCaret);
  if (!match || match.index === undefined) return null;
  const slashOffset = beforeCaret.slice(match.index).indexOf("/");
  if (slashOffset < 0) return null;
  return {
    start: match.index + slashOffset,
    end: caret,
    query: match[1].trim().toLowerCase(),
  };
}

function fuzzyScore(value: string, query: string) {
  const source = value.toLowerCase();
  const needle = query.trim().toLowerCase();
  if (!needle) return 1;
  if (source.includes(needle)) return 100 - source.indexOf(needle);

  let score = 0;
  let sourceIndex = 0;
  let streak = 0;
  for (const char of needle) {
    const found = source.indexOf(char, sourceIndex);
    if (found === -1) return 0;
    streak = found === sourceIndex ? streak + 1 : 1;
    score += 8 + streak * 3 - Math.min(found - sourceIndex, 8);
    sourceIndex = found + 1;
  }
  return score;
}

export function scoreSkill(skill: SkillResponse, query: string) {
  const fields = [
    skill.display_name,
    skill.name,
    skill.description,
    skill.category,
    ...skill.trigger,
  ];
  return Math.max(...fields.map((field) => fuzzyScore(String(field ?? ""), query)));
}

export function scoreBuiltinSlashCommand(command: BuiltinSlashCommand, query: string) {
  const fields = [
    command.name,
    command.displayName,
    command.description,
    command.scope,
    ...command.aliases,
  ];
  return Math.max(...fields.map((field) => fuzzyScore(String(field ?? ""), query)));
}

export function getSkillScopeLabel(skill: SkillResponse) {
  const path = skill.path.toLowerCase();
  if (path.includes("/personal/") || path.includes("/user/")) return "个人";
  return "Skills";
}
