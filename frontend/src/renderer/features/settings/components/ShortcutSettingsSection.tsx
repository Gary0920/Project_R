import { useMemo, useState } from "react";
import type { KeyboardEvent } from "react";

import type { PreferenceState } from "../settingsPreferences";
import {
  DEFAULT_SHORTCUTS,
  SHORTCUT_ACTIONS,
  SHORTCUT_CATEGORY_LABELS,
  findShortcutConflicts,
  mergeShortcuts,
  normalizeShortcutValue,
  shortcutFromKeyboardEvent,
  type ShortcutCategory,
} from "../shortcutRegistry";

type ShortcutSettingsSectionProps = {
  preferences: PreferenceState;
  updatePreference: (next: Partial<PreferenceState>) => void;
};

const CATEGORY_FILTERS: Array<"all" | ShortcutCategory> = ["all", "global", "chat", "composer", "window"];

function renderShortcutKeys(value: string) {
  const normalized = normalizeShortcutValue(value);
  if (!normalized) return <span className="shortcut-empty">未设置</span>;
  return normalized.split("+").map((part) => part.trim()).filter(Boolean).map((part, index, parts) => (
    <span className="shortcut-key-fragment" key={`${part}-${index}`}>
      <kbd>{part}</kbd>
      {index < parts.length - 1 ? <span className="shortcut-key-plus">+</span> : null}
    </span>
  ));
}

export function ShortcutSettingsSection({ preferences, updatePreference }: ShortcutSettingsSectionProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<"all" | ShortcutCategory>("all");
  const [recordingId, setRecordingId] = useState<string | null>(null);
  const shortcuts = useMemo(() => mergeShortcuts(preferences.shortcuts), [preferences.shortcuts]);
  const conflicts = useMemo(() => findShortcutConflicts(shortcuts), [shortcuts]);
  const conflictCount = Array.from(conflicts.values()).filter((items) => items.length > 0).length;
  const normalizedQuery = query.trim().toLowerCase();
  const filteredActions = SHORTCUT_ACTIONS.filter((action) => {
    if (category !== "all" && action.category !== category) return false;
    if (!normalizedQuery) return true;
    return [
      action.label,
      action.description,
      SHORTCUT_CATEGORY_LABELS[action.category],
      shortcuts[action.id],
    ].some((value) => value.toLowerCase().includes(normalizedQuery));
  });

  function updateShortcut(id: string, value: string) {
    updatePreference({
      shortcuts: {
        ...shortcuts,
        [id]: normalizeShortcutValue(value),
      },
    });
  }

  function handleRecorderKeyDown(event: KeyboardEvent<HTMLInputElement>, id: string) {
    if (event.key === "Tab") return;
    event.preventDefault();
    event.stopPropagation();
    if (event.key === "Escape") {
      event.currentTarget.blur();
      setRecordingId(null);
      return;
    }
    if (event.key === "Backspace" || event.key === "Delete") {
      updateShortcut(id, "");
      return;
    }
    const next = shortcutFromKeyboardEvent(event.nativeEvent);
    if (next) updateShortcut(id, next);
  }

  function resetShortcut(id: string) {
    updateShortcut(id, DEFAULT_SHORTCUTS[id] ?? "");
  }

  function resetAllShortcuts() {
    updatePreference({ shortcuts: DEFAULT_SHORTCUTS });
  }

  return (
    <div className="settings-section shortcut-settings">
      <div className="settings-section-header shortcut-settings-header">
        <div>
          <h3>快捷键管理</h3>
          <p>按动作管理快捷键，冲突会在同一作用范围内提示。</p>
        </div>
        <button className="ghost-button" onClick={resetAllShortcuts} type="button">
          全部恢复默认
        </button>
      </div>

      <div className="shortcut-toolbar">
        <input
          aria-label="搜索快捷键动作"
          className="shortcut-search-input"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索动作或快捷键"
          value={query}
        />
        <div className="shortcut-category-tabs" role="tablist" aria-label="快捷键分类">
          {CATEGORY_FILTERS.map((item) => (
            <button
              className={category === item ? "is-active" : ""}
              key={item}
              onClick={() => setCategory(item)}
              type="button"
            >
              {item === "all" ? "全部" : SHORTCUT_CATEGORY_LABELS[item]}
            </button>
          ))}
        </div>
      </div>

      <div className={`shortcut-health ${conflictCount > 0 ? "has-conflict" : ""}`}>
        {conflictCount > 0 ? `发现 ${conflictCount} 个快捷键冲突，请调整后再使用。` : "当前快捷键没有检测到冲突。"}
      </div>

      <div className="shortcut-list">
        {filteredActions.map((action) => {
          const currentShortcut = shortcuts[action.id] ?? "";
          const conflictIds = conflicts.get(action.id) ?? [];
          const conflictLabels = conflictIds
            .map((id) => SHORTCUT_ACTIONS.find((item) => item.id === id)?.label)
            .filter(Boolean)
            .join("、");
          return (
            <div className={`shortcut-row ${conflictIds.length > 0 ? "has-conflict" : ""}`} key={action.id}>
              <div className="shortcut-row-main">
                <div className="shortcut-row-title">
                  <strong>{action.label}</strong>
                  <span>{SHORTCUT_CATEGORY_LABELS[action.category]}</span>
                </div>
                <p>{action.description}</p>
                {conflictLabels ? <small>与「{conflictLabels}」冲突</small> : null}
              </div>
              <div className="shortcut-row-control">
                <input
                  aria-label={`${action.label}快捷键`}
                  className={recordingId === action.id ? "is-recording" : ""}
                  disabled={!action.editable}
                  onBlur={() => setRecordingId(null)}
                  onFocus={() => setRecordingId(action.id)}
                  onKeyDown={(event) => handleRecorderKeyDown(event, action.id)}
                  readOnly
                  value={recordingId === action.id ? "按下新的快捷键" : normalizeShortcutValue(currentShortcut)}
                />
                <div className="shortcut-preview" aria-hidden="true">
                  {renderShortcutKeys(currentShortcut)}
                </div>
                <button
                  className="ghost-button"
                  disabled={!action.editable}
                  onClick={() => resetShortcut(action.id)}
                  type="button"
                >
                  默认
                </button>
                <button
                  className="ghost-button"
                  disabled={!action.editable}
                  onClick={() => updateShortcut(action.id, "")}
                  type="button"
                >
                  清空
                </button>
              </div>
            </div>
          );
        })}
        {filteredActions.length === 0 ? (
          <div className="shortcut-empty-state">没有匹配的快捷键动作。</div>
        ) : null}
      </div>
    </div>
  );
}
