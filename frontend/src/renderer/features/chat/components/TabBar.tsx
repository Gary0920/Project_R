import type { Tab } from "../tabs-state";
import { ChatIcon, NoteIcon, PlusIcon, XmarkIcon } from "../../../shared/icons/LineIcons";

export type TabBarProps = {
  tabs: Tab[];
  activeTabId: string;
  scratchOpen: boolean;
  onSelectTab: (id: string) => void;
  onCloseTab: (id: string) => void;
  onAddChat: () => void;
  onOpenScratch: () => void;
};

export function TabBar({ tabs, activeTabId, scratchOpen, onSelectTab, onCloseTab, onAddChat, onOpenScratch }: TabBarProps) {
  return (
    <div className="tab-bar">
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
            >
              <span className="tab-item-icon">
                <ChatIcon />
              </span>
              <span className="tab-item-title">
                {tab.title}
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
      <div className="tab-drag-spacer" aria-hidden="true" />
    </div>
  );
}
