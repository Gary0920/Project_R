export type ShortcutCategory = "global" | "chat" | "composer" | "window";
export type ShortcutScope = "global" | "composer";

export type ShortcutAction = {
  id: string;
  label: string;
  description: string;
  category: ShortcutCategory;
  scope: ShortcutScope;
  defaultShortcut: string;
  editable: boolean;
};

export const SHORTCUT_CATEGORY_LABELS: Record<ShortcutCategory, string> = {
  global: "全局",
  chat: "对话",
  composer: "输入",
  window: "窗口",
};

export const SHORTCUT_ACTIONS: ShortcutAction[] = [
  {
    id: "search",
    label: "搜索对话",
    description: "打开会话搜索与快速定位入口。",
    category: "global",
    scope: "global",
    defaultShortcut: "Ctrl + K",
    editable: true,
  },
  {
    id: "newChat",
    label: "新建对话",
    description: "在当前工作区创建一个新的聊天会话。",
    category: "chat",
    scope: "global",
    defaultShortcut: "Ctrl + N",
    editable: true,
  },
  {
    id: "settings",
    label: "打开设置",
    description: "打开系统设置弹窗。",
    category: "window",
    scope: "global",
    defaultShortcut: "Ctrl + ,",
    editable: true,
  },
  {
    id: "send",
    label: "发送消息",
    description: "在输入框中提交当前消息。",
    category: "composer",
    scope: "composer",
    defaultShortcut: "Enter",
    editable: true,
  },
  {
    id: "newline",
    label: "输入换行",
    description: "在输入框中插入新行。",
    category: "composer",
    scope: "composer",
    defaultShortcut: "Shift + Enter",
    editable: true,
  },
  {
    id: "cancel",
    label: "取消生成 / 关闭浮层",
    description: "关闭通知面板，或在生成中停止当前回复。",
    category: "global",
    scope: "global",
    defaultShortcut: "Escape",
    editable: false,
  },
];

export const DEFAULT_SHORTCUTS = SHORTCUT_ACTIONS.reduce<Record<string, string>>((acc, action) => {
  acc[action.id] = action.defaultShortcut;
  return acc;
}, {});

const KEY_LABELS: Record<string, string> = {
  " ": "Space",
  arrowdown: "ArrowDown",
  arrowleft: "ArrowLeft",
  arrowright: "ArrowRight",
  arrowup: "ArrowUp",
  esc: "Escape",
  escape: "Escape",
  return: "Enter",
};

function normalizeKeyName(key: string) {
  const trimmed = key.trim();
  if (!trimmed) return "";
  const lower = trimmed.toLowerCase();
  if (KEY_LABELS[lower]) return KEY_LABELS[lower];
  if (trimmed.length === 1) return trimmed.toUpperCase();
  return trimmed[0].toUpperCase() + trimmed.slice(1);
}

export function normalizeShortcutValue(value: string) {
  const parts = value
    .split("+")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return "";

  const key = normalizeKeyName(parts[parts.length - 1]);
  const modifiers = new Set(parts.slice(0, -1).map((part) => part.toLowerCase()));
  const normalized: string[] = [];
  if (modifiers.has("ctrl") || modifiers.has("control")) normalized.push("Ctrl");
  if (modifiers.has("cmd") || modifiers.has("meta") || modifiers.has("command")) normalized.push("Cmd");
  if (modifiers.has("shift")) normalized.push("Shift");
  if (modifiers.has("alt") || modifiers.has("option")) normalized.push("Alt");
  if (key) normalized.push(key);
  return normalized.join(" + ");
}

export function shortcutSignature(value: string) {
  return normalizeShortcutValue(value).toLowerCase().replace(/\s+/g, "");
}

export function shortcutFromKeyboardEvent(event: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "key" | "metaKey" | "shiftKey">) {
  const key = normalizeKeyName(event.key);
  if (!key || ["Control", "Ctrl", "Shift", "Alt", "Meta", "Cmd"].includes(key)) return "";
  const parts: string[] = [];
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.metaKey) parts.push("Cmd");
  if (event.shiftKey) parts.push("Shift");
  if (event.altKey) parts.push("Alt");
  parts.push(key);
  return parts.join(" + ");
}

export function matchesShortcut(
  event: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "key" | "metaKey" | "shiftKey">,
  shortcut: string | undefined,
) {
  if (!shortcut) return false;
  return shortcutSignature(shortcutFromKeyboardEvent(event)) === shortcutSignature(shortcut);
}

export function mergeShortcuts(shortcuts?: Record<string, string>) {
  return { ...DEFAULT_SHORTCUTS, ...(shortcuts ?? {}) };
}

export function findShortcutConflicts(shortcuts: Record<string, string>) {
  const merged = mergeShortcuts(shortcuts);
  const conflicts = new Map<string, string[]>();
  for (const action of SHORTCUT_ACTIONS) {
    if (!action.editable && !merged[action.id]) continue;
    const signature = shortcutSignature(merged[action.id] ?? "");
    if (!signature) continue;
    const conflicting = SHORTCUT_ACTIONS.filter((candidate) => {
      if (candidate.id === action.id) return false;
      if (candidate.scope !== action.scope && candidate.scope !== "global" && action.scope !== "global") return false;
      return shortcutSignature(merged[candidate.id] ?? "") === signature;
    }).map((candidate) => candidate.id);
    if (conflicting.length > 0) conflicts.set(action.id, conflicting);
  }
  return conflicts;
}
