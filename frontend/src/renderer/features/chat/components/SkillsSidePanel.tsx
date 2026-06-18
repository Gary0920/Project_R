import { useState, type MouseEvent, type RefObject } from "react";

import type { SkillResponse } from "../../../shared/api/types";
import { CheckIcon, SearchIcon } from "../../../shared/icons/LineIcons";
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

function SkillSideRow({
  skill,
  selected,
  descriptionVisible,
  onShowDescription,
  onSelect,
}: {
  skill: SkillResponse;
  selected: boolean;
  descriptionVisible: boolean;
  onShowDescription: () => void;
  onSelect: (skill: SkillResponse) => void;
}) {
  return (
    <div
      className={`prompt-row ${selected ? "is-selected" : ""} ${descriptionVisible ? "is-description-visible" : ""}`}
      onMouseEnter={onShowDescription}
    >
      <button
        className="prompt-row-main"
        onClick={() => {
          onShowDescription();
          onSelect(skill);
        }}
        onFocus={onShowDescription}
        type="button"
      >
        <span className="prompt-row-icon is-slash-mark">/</span>
        <span className="prompt-row-copy">
          <span className="prompt-row-title">
            {skill.display_name}
            <span className="prompt-source-badge is-company">Skill</span>
          </span>
          <span className="prompt-row-description">{skill.description}</span>
        </span>
        {selected ? <CheckIcon className="prompt-row-check" /> : null}
      </button>
    </div>
  );
}

function renderSkillRows(
  items: SkillResponse[],
  selectedSkillName: string | null | undefined,
  visibleSkillDescriptionName: string | null,
  setVisibleSkillDescriptionName: (name: string) => void,
  onSelectSkill: (skill: SkillResponse) => void,
) {
  return items.map((skill) => (
    <SkillSideRow
      key={skill.name}
      skill={skill}
      selected={selectedSkillName === skill.name}
      descriptionVisible={visibleSkillDescriptionName === skill.name}
      onShowDescription={() => setVisibleSkillDescriptionName(skill.name)}
      onSelect={onSelectSkill}
    />
  ));
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
  const [visibleSkillDescriptionName, setVisibleSkillDescriptionName] = useState<string | null>(null);
  const [skillSearchQuery, setSkillSearchQuery] = useState("");

  const filteredSkills = skills.filter((skill) => matchesSkillSearch(skill, skillSearchQuery));

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
            <p>选择后应用于本次发送</p>
          </div>
          <button className="prompt-panel-close" onClick={onClose} type="button">×</button>
        </header>
        <div className="prompt-panel-body" onMouseLeave={() => setVisibleSkillDescriptionName(null)}>
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
                renderSkillRows(
                  filteredSkills,
                  selectedSkillName,
                  visibleSkillDescriptionName,
                  setVisibleSkillDescriptionName,
                  onSelectSkill,
                )
              ) : (
                <div className="prompt-empty">{emptyText}</div>
              )}
            </section>
          )}
        </div>
      </aside>
    </aside>
  );
}
