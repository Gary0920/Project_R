import { useEffect, useMemo, useState, type MouseEvent, type RefObject } from "react";

import type { SkillResponse } from "../../../shared/api/types";
import { CheckIcon, SearchIcon, SkillIcon } from "../../../shared/icons/LineIcons";
import { matchesSkillSearch } from "../slashCommands";

export type SkillsSidePanelProps = {
  skills: SkillResponse[];
  selectedSkillName?: string | null;
  auxiliaryPanelResizing: boolean;
  auxiliaryPanelRef: RefObject<HTMLElement | null>;
  auxiliaryPanelWidth: number;
  auxiliaryPanelMaxWidth: () => number;
  onResizeStart: (event: MouseEvent<HTMLDivElement>) => void;
  onClose: () => void;
  onSelectSkill: (skill: SkillResponse) => void;
};

function textFromValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(textFromValue).filter(Boolean).join("、");
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return String(
      record.label
      ?? record.display_name
      ?? record.name
      ?? record.title
      ?? record.description
      ?? record.key
      ?? "",
    );
  }
  return "";
}

function listFromRecords(items: Array<Record<string, unknown>>, fallback: string) {
  const labels = items.map(textFromValue).filter(Boolean);
  return labels.length > 0 ? labels : [fallback];
}

function objectNotes(value: Record<string, unknown>, keys: string[]) {
  return keys.map((key) => textFromValue(value[key])).filter(Boolean);
}

function SkillSideRow({
  skill,
  previewed,
  selected,
  onApply,
  onPreview,
}: {
  skill: SkillResponse;
  previewed: boolean;
  selected: boolean;
  onApply: (skill: SkillResponse) => void;
  onPreview: (skill: SkillResponse) => void;
}) {
  return (
    <div className={`prompt-row ${selected ? "is-selected" : ""} ${previewed ? "is-previewed" : ""}`}>
      <button
        className="prompt-row-main"
        onClick={() => onPreview(skill)}
        onDoubleClick={() => onApply(skill)}
        onFocus={() => onPreview(skill)}
        title={skill.display_name}
        type="button"
      >
        <span className="prompt-row-icon"><SkillIcon /></span>
        <span className="prompt-row-copy">
          <span className="prompt-row-title">
            <span className="prompt-row-name">{skill.display_name}</span>
            <span className="prompt-source-badge is-company">Skill</span>
          </span>
        </span>
      </button>
      <button
        className={`prompt-row-quick-apply ${selected ? "is-selected" : ""}`}
        onClick={(event) => {
          event.stopPropagation();
          onApply(skill);
        }}
        title={selected ? "已应用" : "快速应用"}
        type="button"
      >
        <CheckIcon />
      </button>
    </div>
  );
}

function SkillPreview({ skill, selected }: { skill: SkillResponse | null; selected: boolean }) {
  if (!skill) {
    return (
      <div className="prompt-preview-card is-empty">
        <h3>选择一个 Skill 查看详情</h3>
        <p>单击左侧列表查看用途、所需信息和输出结果；双击列表项或点击应用按钮才会用于本次发送。</p>
      </div>
    );
  }

  const triggerCommands = skill.trigger.length > 0 ? skill.trigger : ["无显式命令"];
  const inputs = listFromRecords(skill.inputs, "无需额外填写信息");
  const outputs = listFromRecords(skill.outputs, "按对话结果输出");
  const notes = [
    ...objectNotes(skill.governance, ["scope", "policy", "note", "description"]),
    ...objectNotes(skill.execution, ["mode", "note", "description"]),
  ];
  const references = skill.references.length > 0 ? skill.references : [];

  return (
    <div className="prompt-preview-card">
      <div className="prompt-preview-header">
        <div>
          <span className="prompt-source-badge is-company">Skill</span>
          <h3>{skill.display_name}</h3>
        </div>
        {selected ? <span className="prompt-preview-applied">已应用</span> : null}
      </div>
      <p>{skill.description || "暂无简介"}</p>
      <div className="skill-command-block">
        <strong>调用命令</strong>
        <div className="skill-command-list">
          {triggerCommands.map((item) => <code key={`command-${item}`}>{item}</code>)}
        </div>
      </div>
      <div className="prompt-preview-detail-grid">
        <div>
          <strong>需要信息</strong>
          <ul>{inputs.map((item) => <li key={`input-${item}`}>{item}</li>)}</ul>
        </div>
        <div>
          <strong>输出结果</strong>
          <ul>{outputs.map((item) => <li key={`output-${item}`}>{item}</li>)}</ul>
        </div>
        {references.length > 0 ? (
          <div>
            <strong>参考资料</strong>
            <ul>{references.map((item) => <li key={`reference-${item}`}>{item}</li>)}</ul>
          </div>
        ) : null}
        {notes.length > 0 ? (
          <div>
            <strong>注意事项</strong>
            <ul>{notes.map((item) => <li key={`note-${item}`}>{item}</li>)}</ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function SkillsSidePanel({
  skills,
  selectedSkillName,
  auxiliaryPanelResizing,
  auxiliaryPanelRef,
  auxiliaryPanelWidth,
  auxiliaryPanelMaxWidth,
  onResizeStart,
  onClose,
  onSelectSkill,
}: SkillsSidePanelProps) {
  const [previewSkillName, setPreviewSkillName] = useState<string | null>(selectedSkillName ?? null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [skillSearchQuery, setSkillSearchQuery] = useState("");

  const filteredSkills = skills.filter((skill) => matchesSkillSearch(skill, skillSearchQuery));
  const previewSkill = useMemo(
    () => skills.find((skill) => skill.name === previewSkillName) ?? null,
    [previewSkillName, skills],
  );

  useEffect(() => {
    if (previewSkillName && skills.some((skill) => skill.name === previewSkillName)) return;
    setPreviewSkillName(selectedSkillName ?? null);
  }, [previewSkillName, selectedSkillName, skills]);

  useEffect(() => {
    if (!skillSearchQuery.trim() || !previewSkillName) return;
    if (filteredSkills.some((skill) => skill.name === previewSkillName)) return;
    const selectedVisibleSkill = filteredSkills.find((skill) => skill.name === selectedSkillName);
    setPreviewSkillName(selectedVisibleSkill?.name ?? filteredSkills[0]?.name ?? null);
  }, [filteredSkills, previewSkillName, selectedSkillName, skillSearchQuery]);

  const emptyText = skills.length === 0
    ? "暂无公司预设 Skill"
    : skillSearchQuery.trim()
      ? "没有匹配的 Skill"
      : "暂无 Skill";

  return (
    <aside
      className={`utility-side-pane auxiliary-side-pane prompt-utility-side-pane ${auxiliaryPanelResizing ? "is-resizing" : ""}`}
      aria-label="Skills 面板"
      ref={auxiliaryPanelRef}
      style={{ flexBasis: auxiliaryPanelWidth, maxWidth: auxiliaryPanelMaxWidth(), width: auxiliaryPanelWidth }}
    >
      <div
        aria-label="调整 Skills 面板宽度"
        aria-orientation="vertical"
        className="utility-resize-handle"
        onMouseDown={onResizeStart}
        role="separator"
        title="调整 Skills 面板宽度"
      />
      <aside className="prompt-panel is-embedded">
        <header className="prompt-panel-header">
          <div>
            <h2>Skills</h2>
          </div>
          <button className="prompt-panel-close" onClick={onClose} type="button">×</button>
        </header>
        <div className={`prompt-panel-body prompt-master-detail ${detailOpen ? "is-detail-open" : ""}`}>
          <div className="prompt-master-pane" aria-label="Skill 列表">
            {skills.length === 0 ? (
              <div className="prompt-empty">暂无可用 Skill</div>
            ) : (
              <section className="prompt-section">
                <div className="prompt-section-head">
                  <div className="prompt-section-title">公司预设</div>
                  <div className="prompt-section-search">
                    <SearchIcon />
                    <input
                      aria-label="搜索公司预设 Skill"
                      onChange={(event) => setSkillSearchQuery(event.target.value)}
                      placeholder="搜索标题或概述"
                      type="search"
                      value={skillSearchQuery}
                    />
                  </div>
                </div>
                {filteredSkills.length > 0 ? (
                  filteredSkills.map((skill) => (
                    <SkillSideRow
                      key={skill.name}
                      skill={skill}
                      previewed={previewSkillName === skill.name}
                      selected={selectedSkillName === skill.name}
                      onApply={onSelectSkill}
                      onPreview={(item) => {
                        setPreviewSkillName(item.name);
                        setDetailOpen(true);
                      }}
                    />
                  ))
                ) : (
                  <div className="prompt-empty">{emptyText}</div>
                )}
              </section>
            )}
          </div>
          <section className="prompt-detail-pane" aria-label="Skill 详情">
            <div className="prompt-detail-toolbar">
              <button className="prompt-detail-back" onClick={() => setDetailOpen(false)} type="button">返回列表</button>
              <div className="prompt-detail-toolbar-actions">
                <button className="prompt-action-button is-apply" disabled={!previewSkill} onClick={() => previewSkill && onSelectSkill(previewSkill)} type="button">
                  应用到本次
                </button>
              </div>
            </div>
            <div className="prompt-detail-scroll">
              <SkillPreview
                skill={previewSkill}
                selected={Boolean(previewSkill && selectedSkillName === previewSkill.name)}
              />
            </div>
          </section>
        </div>
      </aside>
    </aside>
  );
}
