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
  {
    kind: "command",
    name: "doc",
    displayName: "生成 Word",
    description: "将本次要求整理为可下载的 Word 文档。",
    insertText: "/doc ",
    scope: "文件",
    aliases: ["doc", "word", "文档", "文件生成"],
  },
  {
    kind: "command",
    name: "md",
    displayName: "生成 Markdown",
    description: "将本次要求整理为可下载的 Markdown 文件。",
    insertText: "/md ",
    scope: "文件",
    aliases: ["md", "markdown", "markdown 文件"],
  },
  {
    kind: "command",
    name: "txt",
    displayName: "生成文本",
    description: "将本次要求整理为可下载的纯文本文件。",
    insertText: "/txt ",
    scope: "文件",
    aliases: ["txt", "text", "纯文本"],
  },
  {
    kind: "command",
    name: "xlsx",
    displayName: "生成 Excel",
    description: "将本次要求整理为可下载的 Excel 表格。",
    insertText: "/xlsx ",
    scope: "文件",
    aliases: ["xlsx", "excel", "表格", "电子表格"],
  },
  {
    kind: "command",
    name: "pptx",
    displayName: "生成 PPT",
    description: "将本次要求整理为可下载的 PowerPoint 演示文稿。",
    insertText: "/pptx ",
    scope: "文件",
    aliases: ["ppt", "pptx", "powerpoint", "演示文稿"],
  },
  {
    kind: "command",
    name: "pdf",
    displayName: "生成 PDF",
    description: "将 Markdown 或纯文本内容渲染为可下载的 PDF 文件。",
    insertText: "/pdf ",
    scope: "文件",
    aliases: ["pdf", "归档", "发送版"],
  },
  {
    kind: "command",
    name: "email",
    displayName: "生成邮件草稿",
    description: "将本次要求整理为邮件草稿，可复制正文、打开邮件客户端或下载 .eml。",
    insertText: "/email ",
    scope: "邮件",
    aliases: ["email", "eml", "邮件", "邮件草稿", "客户回复"],
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
