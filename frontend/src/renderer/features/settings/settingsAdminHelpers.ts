import type { AdminUserResponse, GBrainToolResponse } from "../../shared/api/types";

export type AdminUserRole = "admin" | "employee";

export type AdminUserConfirmState =
  | { type: "role"; user: AdminUserResponse; nextRole: AdminUserRole }
  | { type: "status"; user: AdminUserResponse; nextActive: boolean }
  | { type: "delete"; user: AdminUserResponse };

export type AdminPasswordDialogState = {
  user: AdminUserResponse;
  password: string;
  resultPassword: string | null;
  copied: boolean;
};

export function roleLabel(role: string) {
  return role === "admin" ? "管理员" : "员工";
}

export function userDisplayName(user: AdminUserResponse) {
  return user.nickname?.trim() || user.username;
}

export function isSystemAccount(user: AdminUserResponse | null | undefined) {
  return Boolean(user?.is_system_account || user?.username === "sysadmin");
}

export function adminConfirmTitle(confirm: AdminUserConfirmState) {
  if (confirm.type === "role") return "确认修改角色";
  if (confirm.type === "delete") return "确认删除账号";
  return confirm.nextActive ? "确认启用账号" : "确认停用账号";
}

export function adminConfirmText(confirm: AdminUserConfirmState) {
  if (confirm.type === "role") {
    return `确定要将 ${userDisplayName(confirm.user)} 的角色更改为 ${roleLabel(confirm.nextRole)} 吗？`;
  }
  if (confirm.type === "delete") {
    return `确定要删除 ${userDisplayName(confirm.user)} 吗？该账号将无法登录，调试数据会被清理，项目文件会转交给当前管理员。`;
  }
  return confirm.nextActive
    ? `确定要启用 ${userDisplayName(confirm.user)} 吗？该用户将恢复登录权限。`
    : `确定要停用 ${userDisplayName(confirm.user)} 吗？该用户将无法登录，但历史记录会保留。`;
}

export function adminConfirmIsDanger(confirm: AdminUserConfirmState) {
  return confirm.type === "delete" || (confirm.type === "status" && !confirm.nextActive);
}

export function generateTemporaryPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const bytes = new Uint32Array(12);
  if (window.crypto?.getRandomValues) {
    window.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = Math.floor(Math.random() * chars.length);
    }
  }
  const body = Array.from(bytes, (value) => chars[value % chars.length]).join("");
  return `Pr${body}!9`;
}

export function statusLabel(value?: string | null) {
  if (!value) return "-";
  const labels: Record<string, string> = {
    ok: "正常",
    registered: "已注册",
    missing: "未注册",
    path_mismatch: "路径不一致",
    unreachable: "不可用",
    auth_required: "缺少 Token",
    disabled: "已禁用",
    oauth_required: "缺 OAuth",
    configured_unverified: "已配置未验收",
    ready: "可执行",
    warnings: "有警告",
    healthy: "健康",
    unhealthy: "异常",
  };
  return labels[value] ?? value;
}

export function yesNo(value?: boolean | null) {
  if (value === true) return "是";
  if (value === false) return "否";
  return "-";
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function recordText(record: Record<string, unknown> | null | undefined, key: string) {
  const value = record?.[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

export function recordNumber(record: Record<string, unknown> | null | undefined, key: string) {
  const value = record?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function toolStatus(response?: GBrainToolResponse | null) {
  return statusLabel(typeof response?.status === "string" ? response.status : response?.ok ? "ok" : undefined);
}

export function toolResultArray(response?: GBrainToolResponse | null, nestedKey?: string): Array<Record<string, unknown>> {
  const result = response?.result;
  if (Array.isArray(result)) {
    return result.map(asRecord).filter(Boolean) as Array<Record<string, unknown>>;
  }
  const record = asRecord(result);
  if (!record) return [];
  const nested = nestedKey ? record[nestedKey] : null;
  if (Array.isArray(nested)) {
    return nested.map(asRecord).filter(Boolean) as Array<Record<string, unknown>>;
  }
  return [];
}

export function shortValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value).slice(0, 140);
  } catch {
    return String(value);
  }
}
