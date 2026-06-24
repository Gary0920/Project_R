import { useEffect, useMemo, useState, type ReactNode } from "react";

import type { Tab } from "../tabs-state";
import type { Workspace } from "../../workspace/state";
import { getWorkspaceAffiliationPath } from "../../workspace/workspaceAffiliation";
import { NoteIcon, PlusIcon, XmarkIcon } from "../../../shared/icons/LineIcons";

export type TabBarProps = {
  tabs: Tab[];
  workspaces: Workspace[];
  activeTabId: string;
  scratchOpen: boolean;
  leadingSlot?: ReactNode;
  trailingSlot?: ReactNode;
  onSelectTab: (id: string) => void;
  onCloseTab: (id: string) => void;
  onAddChat: () => void;
  onOpenScratch: () => void;
};

type TabGroup = {
  id: string;
  workspaceId: number | null;
  label: string;
  tone: TabGroupTone;
  title: string;
  tabs: Tab[];
};

type TabGroupTone = "indigo" | "emerald" | "amber" | "rose" | "slate";

const PROJECT_GROUP_TONES: TabGroupTone[] = ["indigo", "emerald", "amber", "rose", "slate"];

function workspaceGroupId(workspaceId: number | null | undefined) {
  return workspaceId == null ? "workspace-none" : `workspace-${workspaceId}`;
}

function getTabGroupLabel(workspace: Workspace | undefined) {
  if (!workspace) return "未选择";
  if (workspace.workspace_kind === "customer") return "CRM";
  const name = String(workspace.name || "").trim();
  return name || "未命名工作区";
}

function getTabGroupTitle(workspace: Workspace | undefined) {
  return workspace ? getWorkspaceAffiliationPath(workspace) : "未选择工作区";
}

function getTabGroupTone(workspace: Workspace | undefined, fallbackIndex: number): TabGroupTone {
  if (!workspace) return "slate";
  if (workspace.workspace_kind === "user") return "indigo";
  if (workspace.workspace_kind === "customer") return "emerald";
  const seed = Number.isFinite(workspace.id) ? Math.abs(workspace.id) : fallbackIndex;
  return PROJECT_GROUP_TONES[seed % PROJECT_GROUP_TONES.length];
}

export function TabBar({
  tabs,
  workspaces,
  activeTabId,
  scratchOpen,
  leadingSlot,
  trailingSlot,
  onSelectTab,
  onCloseTab,
  onAddChat,
  onOpenScratch,
}: TabBarProps) {
  const [collapsedGroupIds, setCollapsedGroupIds] = useState<Set<string>>(() => new Set());
  const workspaceById = useMemo(() => {
    return new Map(workspaces.map((workspace) => [workspace.id, workspace]));
  }, [workspaces]);
  const visibleTabs = useMemo(() => tabs.filter((tab) => tab.id !== "scratch"), [tabs]);
  const tabGroups = useMemo(() => {
    const groups: TabGroup[] = [];
    const groupById = new Map<string, TabGroup>();

    for (const tab of visibleTabs) {
      const groupId = workspaceGroupId(tab.workspaceId);
      let group = groupById.get(groupId);

      if (!group) {
        const workspace = tab.workspaceId == null ? undefined : workspaceById.get(tab.workspaceId);
        group = {
          id: groupId,
          workspaceId: tab.workspaceId,
          label: getTabGroupLabel(workspace),
          tone: getTabGroupTone(workspace, groups.length),
          title: getTabGroupTitle(workspace),
          tabs: [],
        };
        groupById.set(groupId, group);
        groups.push(group);
      }

      group.tabs.push(tab);
    }

    return groups;
  }, [visibleTabs, workspaceById]);
  const activeGroupId = useMemo(() => {
    const activeTab = visibleTabs.find((tab) => tab.id === activeTabId);
    return activeTab ? workspaceGroupId(activeTab.workspaceId) : "";
  }, [activeTabId, visibleTabs]);
  const shouldShowGroupHeaders = useMemo(() => {
    return tabGroups.length > 1 || tabGroups.some((group) => group.tabs.length > 1);
  }, [tabGroups]);

  useEffect(() => {
    if (!activeGroupId) return;
    setCollapsedGroupIds((current) => {
      if (!current.has(activeGroupId)) return current;
      const next = new Set(current);
      next.delete(activeGroupId);
      return next;
    });
  }, [activeGroupId]);

  function toggleGroup(groupId: string) {
    if (groupId === activeGroupId) return;
    setCollapsedGroupIds((current) => {
      const next = new Set(current);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  }

  function renderTab(tab: Tab, group: TabGroup, standalone = false) {
    const isActive = tab.id === activeTabId;
    return (
      <div
        className={`tab-item ${standalone ? "tab-item-standalone" : ""} ${isActive ? "is-active" : ""}`}
        data-tone={standalone ? group.tone : undefined}
        key={tab.id}
        role="tab"
        aria-selected={isActive}
        onClick={() => onSelectTab(tab.id)}
        title={`${group.title} / ${tab.title}`}
      >
        <span className="tab-item-title">
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
  }

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
        {tabGroups.map((group) => {
          if (!shouldShowGroupHeaders) {
            return renderTab(group.tabs[0], group, true);
          }

          const isActiveGroup = group.id === activeGroupId;
          const isCollapsed = !isActiveGroup && collapsedGroupIds.has(group.id);
          return (
            <div
              className={`tab-group-container ${isActiveGroup ? "is-active" : ""} ${isCollapsed ? "is-collapsed" : ""}`}
              data-tone={group.tone}
              key={group.id}
              role="presentation"
            >
              <button
                aria-expanded={!isCollapsed}
                className="tab-group-label"
                onClick={() => toggleGroup(group.id)}
                title={group.title}
                type="button"
              >
                <span className="tab-group-name">{group.label}</span>
                <span className="tab-group-count">{group.tabs.length}</span>
              </button>
              <div className="tab-group-tabs" role="presentation" aria-hidden={isCollapsed}>
                {group.tabs.map((tab) => renderTab(tab, group))}
              </div>
            </div>
          );
        })}
        <button
          className="tab-add-btn"
          onClick={onAddChat}
          title="新建对话"
          type="button"
        >
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
