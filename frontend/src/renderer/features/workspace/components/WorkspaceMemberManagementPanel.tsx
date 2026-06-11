import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";

import type { ApiClientOptions } from "../../../shared/api/client";
import {
  addWorkspaceAccessGroup,
  getWorkspace,
  listWorkspaceGroupCandidates,
  listWorkspaceMemberCandidates,
  removeWorkspaceMember,
  removeWorkspaceAccessGroup,
  updateWorkspace,
  updateWorkspaceMemberRole,
  upsertWorkspaceMember,
} from "../api";
import type {
  WorkspaceDetailResponse,
  WorkspaceGroupCandidateResponse,
  WorkspaceMemberCandidateResponse,
  WorkspaceMemberResponse,
  WorkspaceResponse,
} from "../../../shared/api/types";
import { parseApiDate } from "../../../shared/utils/time";
import { RefreshIcon, SearchIcon, ShieldIcon, TrashIcon, XmarkIcon } from "../../../shared/icons/LineIcons";

type RoleFilter = "all" | "admin" | "member";
type ComboOption = {
  value: string;
  label: string;
  meta?: string;
  badge?: string;
  disabled?: boolean;
};

export type WorkspaceMemberManagementPanelProps = {
  apiOptions: ApiClientOptions;
  workspace: WorkspaceResponse;
  onClose: () => void;
  onChanged?: () => Promise<void> | void;
};

function roleLabel(role: string, workspaceKind = "project") {
  if (role !== "admin") return "成员";
  return workspaceKind === "customer" ? "客户工作区管理员" : "项目管理员";
}

function roleTone(role: string) {
  return role === "admin" ? "admin" : "member";
}

function displayName(member: WorkspaceMemberResponse) {
  return member.nickname || member.username;
}

function filterComboOptions(options: ComboOption[], value: string, limit = 8) {
  const text = value.trim().toLowerCase();
  return options
    .filter((option) => {
      if (!text) return true;
      return `${option.value} ${option.label} ${option.meta ?? ""}`.toLowerCase().includes(text);
    })
    .slice(0, limit);
}

function SuggestInput({
  value,
  options,
  placeholder,
  disabled,
  icon,
  onChange,
  onSelect,
  onKeyDown,
}: {
  value: string;
  options: ComboOption[];
  placeholder: string;
  disabled?: boolean;
  icon?: ReactNode;
  onChange: (value: string) => void;
  onSelect?: (option: ComboOption) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
}) {
  const [open, setOpen] = useState(false);
  const visibleOptions = filterComboOptions(options, value);
  const showMenu = open && visibleOptions.length > 0;
  return (
    <div className="workspace-suggest-input">
      <label className={icon ? "has-icon" : ""}>
        {icon}
        <input
          disabled={disabled}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          value={value}
        />
      </label>
      {showMenu ? (
        <div className="workspace-suggest-menu" role="listbox">
          {visibleOptions.map((option) => (
            <button
              disabled={option.disabled}
              key={`${option.value}-${option.badge ?? ""}`}
              onMouseDown={(event) => {
                event.preventDefault();
                if (option.disabled) return;
                onChange(option.value);
                onSelect?.(option);
                setOpen(false);
              }}
              role="option"
              type="button"
            >
              <span>
                <strong>{option.label}</strong>
                {option.meta ? <small>{option.meta}</small> : null}
              </span>
              {option.badge ? <em>{option.badge}</em> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function WorkspaceMemberManagementPanel({ apiOptions, workspace, onClose, onChanged }: WorkspaceMemberManagementPanelProps) {
  const [detail, setDetail] = useState<WorkspaceDetailResponse | null>(null);
  const [memberCandidates, setMemberCandidates] = useState<WorkspaceMemberCandidateResponse[]>([]);
  const [groupCandidates, setGroupCandidates] = useState<WorkspaceGroupCandidateResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviteUsername, setInviteUsername] = useState("");
  const [inviteRole, setInviteRole] = useState<"member" | "admin">("member");
  const [submitting, setSubmitting] = useState(false);
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [busyGroupName, setBusyGroupName] = useState<string | null>(null);
  const [visibilityBusy, setVisibilityBusy] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");

  const members = detail?.members ?? [];
  const accessGroups = detail?.access_groups ?? [];
  const workspaceKind = detail?.workspace_kind ?? workspace.workspace_kind;
  const isCustomerWorkspace = workspaceKind === "customer";
  const isHidden = detail?.is_hidden ?? workspace.is_hidden;
  const adminCount = members.filter((member) => member.role === "admin").length;
  const filteredMembers = useMemo(() => {
    const text = query.trim().toLowerCase();
    return members.filter((member) => {
      if (roleFilter !== "all" && member.role !== roleFilter) return false;
      if (!text) return true;
      return `${member.username} ${member.nickname ?? ""}`.toLowerCase().includes(text);
    });
  }, [members, query, roleFilter]);
  const inviteOptions = useMemo<ComboOption[]>(() => {
    const memberIds = new Set(members.map((member) => member.user_id));
    return memberCandidates.map((candidate) => ({
      value: candidate.username,
      label: candidate.nickname ? `${candidate.nickname} · @${candidate.username}` : `@${candidate.username}`,
      meta: [candidate.work_group ? `组别：${candidate.work_group}` : "", candidate.role === "admin" ? "系统管理员" : "员工"]
        .filter(Boolean)
        .join(" · "),
      badge: memberIds.has(candidate.user_id)
        ? candidate.member_role === "admin" ? `已是${roleLabel("admin", workspaceKind)}` : "已是成员"
        : "可添加",
    }));
  }, [memberCandidates, members]);
  const groupOptions = useMemo<ComboOption[]>(() => {
    const authorized = new Set(accessGroups);
    return groupCandidates.map((candidate) => ({
      value: candidate.group_name,
      label: candidate.group_name,
      meta: candidate.source === "workspace" ? "当前项目授权组" : "来自用户组别",
      badge: authorized.has(candidate.group_name) || candidate.is_authorized ? "已授权" : "可添加",
      disabled: authorized.has(candidate.group_name) || candidate.is_authorized,
    }));
  }, [accessGroups, groupCandidates]);
  const memberSearchOptions = useMemo<ComboOption[]>(() =>
    members.map((member) => ({
      value: member.username,
      label: displayName(member),
      meta: `@${member.username}`,
      badge: roleLabel(member.role, workspaceKind),
    })),
  [members, workspaceKind]);

  async function refreshCandidateLists() {
    const [nextMembers, nextGroups] = await Promise.all([
      listWorkspaceMemberCandidates(apiOptions, workspace.id),
      listWorkspaceGroupCandidates(apiOptions, workspace.id),
    ]);
    setMemberCandidates(nextMembers);
    setGroupCandidates(nextGroups);
  }

  async function refreshMembers() {
    setLoading(true);
    setError(null);
    try {
      const nextDetail = await getWorkspace(apiOptions, workspace.id);
      setDetail(nextDetail);
      await refreshCandidateLists();
    } catch (loadError: unknown) {
      setError(loadError instanceof Error ? loadError.message : "无法读取成员列表");
    } finally {
      setLoading(false);
    }
  }

  async function handleInvite() {
    if (!inviteUsername.trim()) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await upsertWorkspaceMember(apiOptions, workspace.id, {
        username: inviteUsername.trim(),
        role: inviteRole,
      });
      setInviteUsername("");
      setInviteRole("member");
      setNotice("成员权限已更新");
      await refreshMembers();
      await onChanged?.();
    } catch (inviteError: unknown) {
      setError(inviteError instanceof Error ? inviteError.message : "添加成员失败");
    } finally {
      setSubmitting(false);
    }
  }

  function handleInviteKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") void handleInvite();
  }

  async function handleRoleChange(member: WorkspaceMemberResponse, role: "admin" | "member") {
    if (member.role === role) return;
    setBusyUserId(member.user_id);
    setError(null);
    setNotice(null);
    try {
      await updateWorkspaceMemberRole(apiOptions, workspace.id, member.user_id, role);
      setNotice(`${displayName(member)} 已设为${roleLabel(role, workspaceKind)}`);
      await refreshMembers();
      await onChanged?.();
    } catch (roleError: unknown) {
      setError(roleError instanceof Error ? roleError.message : "修改角色失败");
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleRemove(member: WorkspaceMemberResponse) {
    if (!window.confirm(`移除 ${displayName(member)} 的项目访问权限？`)) return;
    setBusyUserId(member.user_id);
    setError(null);
    setNotice(null);
    try {
      await removeWorkspaceMember(apiOptions, workspace.id, member.user_id);
      setNotice(`${displayName(member)} 已移除`);
      await refreshMembers();
      await onChanged?.();
    } catch (removeError: unknown) {
      setError(removeError instanceof Error ? removeError.message : "移除成员失败");
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleVisibilityChange(nextHidden: boolean) {
    setVisibilityBusy(true);
    setError(null);
    setNotice(null);
    try {
      await updateWorkspace(apiOptions, workspace.id, { is_hidden: nextHidden });
      setNotice(nextHidden ? "工作区已设为隐藏，仅白名单人员或组别可搜索和进入" : "工作区已设为开放，所有用户均可搜索和进入");
      await refreshMembers();
      await onChanged?.();
    } catch (visibilityError: unknown) {
      setError(visibilityError instanceof Error ? visibilityError.message : "修改项目可见性失败");
    } finally {
      setVisibilityBusy(false);
    }
  }

  async function handleAddGroup() {
    if (!groupName.trim()) return;
    setBusyGroupName(groupName.trim());
    setError(null);
    setNotice(null);
    try {
      await addWorkspaceAccessGroup(apiOptions, workspace.id, groupName.trim());
      setNotice(`${groupName.trim()} 组已加入受限工作区访问白名单`);
      setGroupName("");
      await refreshMembers();
      await onChanged?.();
    } catch (groupError: unknown) {
      setError(groupError instanceof Error ? groupError.message : "添加组别失败");
    } finally {
      setBusyGroupName(null);
    }
  }

  async function handleRemoveGroup(name: string) {
    setBusyGroupName(name);
    setError(null);
    setNotice(null);
    try {
      await removeWorkspaceAccessGroup(apiOptions, workspace.id, name);
      setNotice(`${name} 组已移出受限工作区访问白名单`);
      await refreshMembers();
      await onChanged?.();
    } catch (groupError: unknown) {
      setError(groupError instanceof Error ? groupError.message : "移除组别失败");
    } finally {
      setBusyGroupName(null);
    }
  }

  useEffect(() => {
    void refreshMembers();
  }, [apiOptions, workspace.id]);

  return (
    <div className="workspace-member-overlay" onClick={onClose}>
      <section className="workspace-member-drawer" aria-label="工作区成员管理" onClick={(event) => event.stopPropagation()}>
        <header className="workspace-member-drawer-header">
          <span className="workspace-member-drawer-icon"><ShieldIcon /></span>
          <div>
            <h2>成员管理</h2>
            <p>{isCustomerWorkspace ? "CRM" : workspace.brand || "PROJECT"} · {workspace.name}</p>
          </div>
          <button className="workspace-member-close" onClick={onClose} title="关闭" type="button"><XmarkIcon /></button>
        </header>

        <div className="workspace-member-summary">
          <span><strong>{members.length}</strong><small>总成员</small></span>
          <span><strong>{adminCount}</strong><small>项目管理员</small></span>
          <span><strong>{accessGroups.length}</strong><small>授权组别</small></span>
        </div>

        <section className="workspace-visibility-panel" aria-label="工作区可见性">
          <div>
            <strong>{isCustomerWorkspace ? "受限客户工作区" : isHidden ? "隐藏项目" : "开放项目"}</strong>
            <span>
              {isCustomerWorkspace
                ? "CRM 默认只允许系统管理员、成员或授权组别搜索和进入。"
                : isHidden ? "仅白名单人员或组别可搜索和进入该项目。" : "所有用户均可搜索和进入该项目；成员列表只用于项目管理员和敏感项目白名单。"}
            </span>
          </div>
          <button disabled={visibilityBusy || isCustomerWorkspace} onClick={() => void handleVisibilityChange(!isHidden)} type="button">
            {isHidden ? "改为开放" : "设为隐藏"}
          </button>
        </section>

        <section className="workspace-member-invite-panel" aria-label="添加或更新成员">
          <SuggestInput
            onChange={setInviteUsername}
            onKeyDown={handleInviteKeyDown}
            placeholder="用户名"
            options={inviteOptions}
            value={inviteUsername}
          />
          <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as "member" | "admin")}>
            <option value="member">成员</option>
            <option value="admin">{roleLabel("admin", workspaceKind)}</option>
          </select>
          <button disabled={submitting || !inviteUsername.trim()} onClick={() => void handleInvite()} type="button">添加/更新</button>
        </section>

        <section className="workspace-group-panel" aria-label="隐藏项目组别白名单">
          <div className="workspace-group-add">
            <SuggestInput
              onChange={setGroupName}
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleAddGroup();
              }}
              options={groupOptions}
              placeholder="组别，例如：销售部 / 管理层"
              value={groupName}
            />
            <button disabled={!groupName.trim() || Boolean(busyGroupName)} onClick={() => void handleAddGroup()} type="button">添加组别</button>
          </div>
          <div className="workspace-group-list">
            {accessGroups.length ? accessGroups.map((name) => (
              <span key={name}>
                <strong>{name}</strong>
                <button disabled={busyGroupName === name} onClick={() => void handleRemoveGroup(name)} type="button">移除</button>
              </span>
            )) : <small>暂无授权组别。受限工作区可通过下方成员或这里的组别授权访问。</small>}
          </div>
        </section>

        <div className="workspace-member-toolbar">
          <SuggestInput
            icon={<SearchIcon />}
            onChange={setQuery}
            options={memberSearchOptions}
            placeholder="搜索成员"
            value={query}
          />
          <div className="workspace-member-role-filter" role="tablist" aria-label="成员角色筛选">
            {(["all", "admin", "member"] as RoleFilter[]).map((role) => (
              <button
                className={roleFilter === role ? "is-active" : ""}
                key={role}
                onClick={() => setRoleFilter(role)}
                type="button"
              >
                {role === "all" ? "全部" : roleLabel(role, workspaceKind)}
              </button>
            ))}
          </div>
          <button className="workspace-member-refresh" disabled={loading} onClick={() => void refreshMembers()} title="刷新" type="button"><RefreshIcon /></button>
        </div>

        {error ? <p className="workspace-member-status is-error">{error}</p> : null}
        {notice ? <p className="workspace-member-status is-success">{notice}</p> : null}

        <div className="workspace-member-table" role="table" aria-label="工作区成员">
          <div className="workspace-member-table-head" role="row">
            <span>成员</span>
            <span>角色</span>
            <span>加入时间</span>
            <span>操作</span>
          </div>
          {loading ? <p className="workspace-member-table-empty">正在读取成员...</p> : null}
          {!loading && filteredMembers.length === 0 ? <p className="workspace-member-table-empty">没有匹配成员</p> : null}
          {!loading && filteredMembers.map((member) => (
            <div className="workspace-member-table-row" key={member.user_id} role="row">
              <span className="workspace-member-person">
                <strong>{displayName(member)}</strong>
                <small>@{member.username}</small>
              </span>
              <span>
                <select
                  disabled={busyUserId === member.user_id}
                  onChange={(event) => void handleRoleChange(member, event.target.value as "admin" | "member")}
                  value={member.role}
                >
                  <option value="member">成员</option>
                  <option value="admin">{roleLabel("admin", workspaceKind)}</option>
                </select>
                <em className={`workspace-member-role-badge is-${roleTone(member.role)}`}>{roleLabel(member.role, workspaceKind)}</em>
              </span>
              <span className="workspace-member-date">{parseApiDate(member.joined_at).toLocaleDateString("zh-CN")}</span>
              <span>
                <button disabled={busyUserId === member.user_id} onClick={() => void handleRemove(member)} type="button">
                  <TrashIcon />
                  <span>移除</span>
                </button>
              </span>
            </div>
          ))}
        </div>

        <footer className="workspace-member-policy">
          <span><strong>开放项目</strong><small>所有用户均可搜索和进入，成员列表不代表全部访问者。</small></span>
          <span><strong>受限工作区</strong><small>仅系统管理员、成员和授权组别可搜索和进入。</small></span>
          <span><strong>工作区管理员</strong><small>可重命名工作区、维护人员和组别。</small></span>
        </footer>
      </section>
    </div>
  );
}
