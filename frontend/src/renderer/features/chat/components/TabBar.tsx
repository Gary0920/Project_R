import type { ReactNode } from "react";

import type { Tab } from "../tabs-state";
import { ChatIcon, NoteIcon, PlusIcon, XmarkIcon } from "../../../shared/icons/LineIcons";

export type TabBarProps = {
  tabs: Tab[];
  activeTabId: string;
  scratchOpen: boolean;
  workspaceAffiliationLabel: string;
  workspaceAffiliationPath: string;
  leadingSlot?: ReactNode;
  trailingSlot?: ReactNode;
  onSelectTab: (id: string) => void;
  onCloseTab: (id: string) => void;
  onAddChat: () => void;
  onOpenScratch: () => void;
};

export function TabBar({
  tabs,
  activeTabId,
  scratchOpen,
  workspaceAffiliationLabel,
  workspaceAffiliationPath,
  leadingSlot,
  trailingSlot,
  onSelectTab,
  onCloseTab,
  onAddChat,
  onOpenScratch,
}: TabBarProps) {
  return (
    <header className="workbench-titlebar" aria-label="工作台标题栏">
      {leadingSlot ? <div className="workbench-titlebar-leading">{leadingSlot}</div> : null}
      <div className="tab-strip titlebar-no-drag" role="tablist" aria-label="标签页">
        <button
          className={`tab-note-btn ${scratchOpen ? "is-active" : ""}`}
          onClick={onOpenScratch}
          title="快速笔记"
          type="button"
        >
          <NoteIcon />
        </button>
        {tabs.filter((tab) => tab.id !== "scratch").map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <div
              className={`tab-item ${isActive ? "is-active" : ""}`}
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => onSelectTab(tab.id)}
              title={isActive ? workspaceAffiliationPath : undefined}
            >
              <span className="tab-item-icon">
                <ChatIcon />
              </span>
              <span className="tab-item-title">
                {isActive ? (
                  <>
                    <span className="tab-item-affiliation">{workspaceAffiliationLabel}</span>
                    <span aria-hidden className="tab-item-title-sep">·</span>
                  </>
                ) : null}
                <span className="tab-item-title-text">{tab.title}</span>
              </span>
              <span
                  className="tab-item-close"
                  onClick={(e) => {
                    e.stopPropagation();
                    onCloseTab(tab.id);
                  }}
                  title="关闭标签"
                >
                  <XmarkIcon />
                </span>
            </div>
          );
        })}
        <button className="tab-add-btn" onClick={onAddChat} title="新建对话" type="button">
          <PlusIcon />
        </button>
      </div>
      <div className="titlebar-drag-spacer" aria-hidden="true" />
      {trailingSlot ? (
        <div className="workbench-system-tools titlebar-no-drag" aria-label="系统工具">
          {trailingSlot}
        </div>
      ) : null}
    </header>
  );
}
