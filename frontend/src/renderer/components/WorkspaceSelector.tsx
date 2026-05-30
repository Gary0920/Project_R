import { useEffect, useMemo, useState, type DragEvent, type KeyboardEvent } from "react";
import { useAtom } from "jotai";
import {
  createWorkspace,
  deleteWorkspace,
  joinWorkspace,
  listWorkspaces,
  searchWorkspaces,
  updateWorkspace,
} from "../api/workspaces";
import { ApiError } from "../api/client";
import {
  activeWorkspaceIdAtom,
  workspacesAtom,
  type Workspace,
} from "../atoms/workspace-atoms";
import type { WorkspaceSearchResult } from "../api/types";
import { createApiOptions } from "../pages/AppPage";
import {
  ChevronDownIcon,
  EditIcon,
  PlusIcon,
  SearchIcon,
  TrashIcon,
  WorkspaceIcon,
} from "./LineIcons";

export type WorkspaceSelectorProps = {
  apiOptions: ReturnType<typeof createApiOptions>;
  onWorkspaceChanged?: (workspaceId: number | null) => void;
};

const ORDER_KEY = "project_r_workspace_order";
const BRANDS = ["AURA", "BFI", "SPECWISE", "SYNOVA"];
type DirectoryWorkspace = WorkspaceSearchResult;

function readOrder() {
  try {
    return JSON.parse(localStorage.getItem(ORDER_KEY) ?? "[]") as number[];
  } catch {
    return [];
  }
}

function sortByOrder(items: Workspace[], order: number[]) {
  const defaults = items.filter((item) => item.is_default);
  const projects = items.filter((item) => !item.is_default);
  if (order.length === 0) return [...defaults, ...projects];
  const weight = new Map(order.map((id, index) => [id, index]));
  projects.sort((a, b) => {
    const aw = weight.get(a.id) ?? Number.MAX_SAFE_INTEGER;
    const bw = weight.get(b.id) ?? Number.MAX_SAFE_INTEGER;
    if (aw !== bw) return aw - bw;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
  return [...defaults, ...projects];
}

function sortDirectoryProjects(a: DirectoryWorkspace, b: DirectoryWorkspace) {
  if (a.is_member !== b.is_member) return a.is_member ? -1 : 1;
  const at = new Date(a.updated_at).getTime();
  const bt = new Date(b.updated_at).getTime();
  if (at !== bt) return bt - at;
  return a.name.localeCompare(b.name, "zh-Hans-CN");
}

export function WorkspaceSelector({ apiOptions, onWorkspaceChanged }: WorkspaceSelectorProps) {
  const [workspaces, setWorkspaces] = useAtom(workspacesAtom);
  const [activeWorkspaceId, setActiveWorkspaceId] = useAtom(activeWorkspaceIdAtom);
  const [isOpen, setIsOpen] = useState(true);
  const [directoryOpen, setDirectoryOpen] = useState(false);
  const [directoryQuery, setDirectoryQuery] = useState("");
  const [directoryResults, setDirectoryResults] = useState<DirectoryWorkspace[]>([]);
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newBrand, setNewBrand] = useState("BFI");
  const [createError, setCreateError] = useState("");
  const [renameInput, setRenameInput] = useState<{ id: number; value: string } | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const activeWorkspace = workspaces.find((item) => item.id === activeWorkspaceId);
  const queryText = directoryQuery.trim();
  const brandSummaries = useMemo(() => {
    return BRANDS.map((brand) => ({
      brand,
      items: directoryResults.filter((item) => item.brand === brand),
    }));
  }, [directoryResults]);
  const groupedSearchResults = useMemo(() => {
    return BRANDS.map((brand) => ({
      brand,
      items: directoryResults
        .filter((item) => item.brand === brand)
        .sort(sortDirectoryProjects),
    })).filter((group) => group.items.length > 0);
  }, [directoryResults]);
  const visibleProjects = useMemo(() => {
    const filtered = selectedBrand && !queryText
      ? directoryResults.filter((item) => item.brand === selectedBrand)
      : directoryResults;
    return [...filtered].sort(sortDirectoryProjects);
  }, [directoryResults, queryText, selectedBrand]);

  async function reloadWorkspaces(preferredId?: number | null) {
    const loaded = sortByOrder(await listWorkspaces(apiOptions), readOrder());
    setWorkspaces(loaded);
    const nextId = preferredId ?? activeWorkspaceId ?? loaded[0]?.id ?? null;
    if (nextId !== activeWorkspaceId) {
      setActiveWorkspaceId(nextId);
      onWorkspaceChanged?.(nextId);
    }
    return loaded;
  }

  useEffect(() => {
    let mounted = true;
    listWorkspaces(apiOptions)
      .then((loaded) => {
        if (!mounted) return;
        const ordered = sortByOrder(loaded, readOrder());
        setWorkspaces(ordered);
        if (!activeWorkspaceId && ordered[0]) {
          setActiveWorkspaceId(ordered[0].id);
          onWorkspaceChanged?.(ordered[0].id);
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!directoryOpen) return;
    const timer = window.setTimeout(() => {
      const query = directoryQuery.trim();
      searchWorkspaces(apiOptions, query, query ? null : selectedBrand)
        .then((results) => setDirectoryResults(results))
        .catch(() => setDirectoryResults([]));
    }, 160);
    return () => window.clearTimeout(timer);
  }, [apiOptions, directoryOpen, directoryQuery, selectedBrand]);

  function persistOrder(next: Workspace[]) {
    localStorage.setItem(ORDER_KEY, JSON.stringify(next.filter((item) => !item.is_default).map((item) => item.id)));
  }

  function setOrderedWorkspaces(next: Workspace[]) {
    persistOrder(next);
    setWorkspaces(sortByOrder(next, readOrder()));
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    try {
      const workspace = await createWorkspace(apiOptions, name, newDescription.trim(), newBrand);
      await reloadWorkspaces(workspace.id);
      setSelectedBrand(workspace.brand || newBrand);
      setDirectoryQuery("");
      const results = await searchWorkspaces(apiOptions, "", workspace.brand || newBrand);
      setDirectoryResults(results);
      setCreating(false);
      setNewName("");
      setNewDescription("");
      setCreateError("");
    } catch (error) {
      setCreateError(error instanceof ApiError ? error.message : "新建项目失败，请稍后重试。");
    }
  }

  function handleCreateKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") void handleCreate();
    if (event.key === "Escape") setCreating(false);
  }

  function isJoined(workspace: DirectoryWorkspace) {
    return workspace.is_member || workspaces.some((item) => item.id === workspace.id);
  }

  function openJoinedWorkspace(workspace: DirectoryWorkspace) {
    setActiveWorkspaceId(workspace.id);
    onWorkspaceChanged?.(workspace.id);
    setDirectoryOpen(false);
  }

  async function handleDirectoryProject(workspace: DirectoryWorkspace) {
    if (isJoined(workspace)) {
      openJoinedWorkspace(workspace);
      return;
    }
    await joinWorkspace(apiOptions, workspace.id);
    await reloadWorkspaces(workspace.id);
    setDirectoryOpen(false);
  }

  async function commitRename() {
    if (!renameInput) return;
    const name = renameInput.value.trim();
    const current = workspaces.find((item) => item.id === renameInput.id);
    if (!current || !current.can_rename || !name || name === current.name) {
      setRenameInput(null);
      return;
    }
    setWorkspaces((prev) => prev.map((item) => item.id === current.id ? { ...item, name } : item));
    setRenameInput(null);
    try {
      const updated = await updateWorkspace(apiOptions, current.id, { name });
      setWorkspaces((prev) => prev.map((item) => item.id === updated.id ? updated : item));
    } catch {
      await reloadWorkspaces();
    }
  }

  function handleDragStart(index: number) {
    if (workspaces[index]?.is_default) return;
    setDragIndex(index);
  }

  function handleDragOver(event: DragEvent) {
    event.preventDefault();
  }

  function handleDrop(event: DragEvent, targetIndex: number) {
    event.preventDefault();
    event.stopPropagation();
    if (dragIndex === null || dragIndex === targetIndex || workspaces[targetIndex]?.is_default) {
      setDragIndex(null);
      return;
    }
    const next = [...workspaces];
    const [moved] = next.splice(dragIndex, 1);
    next.splice(targetIndex, 0, moved);
    setOrderedWorkspaces(next);
    setDragIndex(null);
  }

  async function handleDelete(workspace: Workspace) {
    if (!workspace.can_delete) return;
    try {
      await deleteWorkspace(apiOptions, workspace.id);
      const next = workspaces.filter((item) => item.id !== workspace.id);
      setOrderedWorkspaces(next);
      if (activeWorkspaceId === workspace.id) {
        const fallback = next[0]?.id ?? null;
        setActiveWorkspaceId(fallback);
        onWorkspaceChanged?.(fallback);
      }
    } catch {
      // Deletion can be blocked by backend permissions; leave list unchanged.
    }
  }

  function renderProjectRow(workspace: DirectoryWorkspace) {
    const joined = isJoined(workspace);
    return (
      <button
        className={`project-directory-row ${joined ? "is-joined" : ""}`}
        key={workspace.id}
        onClick={() => void handleDirectoryProject(workspace)}
        type="button"
      >
        <span className="project-directory-row-main">
          <strong>{workspace.name}</strong>
          <small>{workspace.slug}</small>
        </span>
        <span className="project-directory-row-meta">{workspace.member_count} 人</span>
        <span className="project-directory-row-status">{joined ? "已加入" : "未加入"}</span>
        <b>{joined ? "打开" : "加入"}</b>
      </button>
    );
  }

  return (
    <div className="workspace-selector-area">
      <div className="workspace-section-header">
        <button
          className="workspace-section-toggle"
          onClick={() => setIsOpen((current) => !current)}
          title="工作区"
          type="button"
        >
          <span className="workspace-section-title">
            <WorkspaceIcon />
            <span>工作区</span>
            {activeWorkspace ? <small>{activeWorkspace.name}</small> : null}
          </span>
          <ChevronDownIcon className={isOpen ? "workspace-chevron is-open" : "workspace-chevron"} />
        </button>
        <button
          className="workspace-create-icon"
          onClick={() => {
            setDirectoryOpen(true);
            setCreating(false);
            setCreateError("");
            setDirectoryQuery("");
            setSelectedBrand(null);
          }}
          title="项目目录"
          type="button"
        >
          <SearchIcon />
        </button>
      </div>

      {isOpen ? (
        <div className="workspace-list">
          {workspaces.map((workspace, index) => (
            <div
              className={`workspace-list-item ${workspace.id === activeWorkspaceId ? "is-active" : ""} ${dragIndex === index ? "is-dragging" : ""}`}
              draggable={!workspace.is_default}
              key={workspace.id}
              onClick={() => {
                setActiveWorkspaceId(workspace.id);
                onWorkspaceChanged?.(workspace.id);
              }}
              onDragStart={() => handleDragStart(index)}
              onDragOver={handleDragOver}
              onDrop={(event) => handleDrop(event, index)}
              onDragEnd={() => setDragIndex(null)}
              role="button"
              tabIndex={0}
            >
              <WorkspaceIcon className="workspace-item-icon" />
              {renameInput?.id === workspace.id ? (
                <input
                  autoFocus
                  className="workspace-rename-input"
                  onBlur={() => void commitRename()}
                  onChange={(event) => setRenameInput({ id: workspace.id, value: event.target.value })}
                  onClick={(event) => event.stopPropagation()}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void commitRename();
                    if (event.key === "Escape") setRenameInput(null);
                  }}
                  value={renameInput.value}
                />
              ) : (
                <span className="workspace-list-name">{workspace.name}</span>
              )}
              {workspace.is_default ? <span className="workspace-default-badge">私人</span> : <span className="workspace-default-badge">{workspace.brand}</span>}
              <div className="workspace-row-actions" onClick={(event) => event.stopPropagation()}>
                <button
                  disabled={!workspace.can_rename}
                  onClick={() => setRenameInput({ id: workspace.id, value: workspace.name })}
                  title={workspace.can_rename ? "重命名" : "默认工作区不能重命名"}
                  type="button"
                >
                  <EditIcon />
                </button>
                <button
                  disabled={!workspace.can_delete}
                  onClick={() => void handleDelete(workspace)}
                  title={workspace.can_delete ? "删除工作区" : "默认工作区不能删除"}
                  type="button"
                >
                  <TrashIcon />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {directoryOpen ? (
        <div className="project-directory-overlay" onClick={() => setDirectoryOpen(false)}>
          <section className="project-directory-panel" onClick={(event) => event.stopPropagation()}>
            <header className="project-directory-header">
              <div>
                <h2>项目目录</h2>
                <p>搜索、加入、打开或新建公司项目。</p>
              </div>
              <button className="prompt-panel-close" onClick={() => setDirectoryOpen(false)} type="button">×</button>
            </header>
            <div className="project-directory-toolbar">
              <label className="project-directory-search">
                <SearchIcon />
                <input
                  autoFocus
                  onChange={(event) => setDirectoryQuery(event.target.value)}
                  placeholder="搜索项目代号或名称"
                  value={directoryQuery}
                />
              </label>
              <button className="project-directory-new" onClick={() => setCreating((value) => !value)} type="button">
                <PlusIcon />
                <span>新建项目</span>
              </button>
            </div>
            {creating ? (
              <div className="project-directory-create">
                <select value={newBrand} onChange={(event) => setNewBrand(event.target.value)}>
                  {BRANDS.map((brand) => <option key={brand} value={brand}>{brand}</option>)}
                </select>
                <input value={newName} onChange={(event) => setNewName(event.target.value)} onKeyDown={handleCreateKeyDown} placeholder="项目代号，例如 BG001" />
                <input value={newDescription} onChange={(event) => setNewDescription(event.target.value)} placeholder="项目说明，可选" />
                <button disabled={!newName.trim()} onClick={() => void handleCreate()} type="button">创建</button>
                {createError ? <p>{createError}</p> : null}
              </div>
            ) : null}
            {queryText ? (
              <div className="project-directory-results">
                <div className="project-directory-view-header">
                  <h3>搜索结果</h3>
                  <span>{visibleProjects.length} 个匹配项目</span>
                </div>
                {groupedSearchResults.length ? groupedSearchResults.map((group) => (
                  <section className="project-directory-result-group" key={group.brand}>
                    <h4>{group.brand}</h4>
                    <div className="project-directory-rows">
                      {group.items.map(renderProjectRow)}
                    </div>
                  </section>
                )) : <p className="project-directory-empty">没有匹配项目</p>}
              </div>
            ) : selectedBrand ? (
              <div className="project-directory-results">
                <div className="project-directory-view-header">
                  <button className="project-directory-back" onClick={() => setSelectedBrand(null)} type="button">← 返回</button>
                  <h3>{selectedBrand} · {visibleProjects.length} 个项目</h3>
                </div>
                {visibleProjects.length ? (
                  <div className="project-directory-rows">
                    {visibleProjects.map(renderProjectRow)}
                  </div>
                ) : <p className="project-directory-empty">暂无项目</p>}
              </div>
            ) : (
              <div className="project-directory-brand-grid">
                {brandSummaries.map((group) => {
                  const joinedCount = group.items.filter((workspace) => isJoined(workspace)).length;
                  const previewItems = [...group.items].sort(sortDirectoryProjects).slice(0, 2);
                  return (
                    <button
                      className="project-directory-brand-card"
                      key={group.brand}
                      onClick={() => setSelectedBrand(group.brand)}
                      type="button"
                    >
                      <span>
                        <strong>{group.brand}</strong>
                        <em>{group.items.length} 个项目 · 已加入 {joinedCount}</em>
                      </span>
                      {previewItems.length ? (
                        <small>{previewItems.map((workspace) => workspace.name).join(" / ")}</small>
                      ) : (
                        <small>暂无项目</small>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
