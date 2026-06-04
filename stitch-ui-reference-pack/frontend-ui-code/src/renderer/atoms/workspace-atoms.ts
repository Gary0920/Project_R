import { atom } from "jotai";

export type Workspace = {
  id: number;
  name: string;
  slug: string;
  description: string;
  created_by: number;
  member_count: number;
  brand: string;
  workspace_kind: string;
  is_default: boolean;
  is_hidden: boolean;
  can_rename: boolean;
  can_delete: boolean;
  storage_path?: string;
  members?: WorkspaceMember[];
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

export type WorkspaceMember = {
  user_id: number;
  username: string;
  nickname: string;
  role: "admin" | "member";
  joined_at: string;
};

export const workspacesAtom = atom<Workspace[]>([]);
export const activeWorkspaceIdAtom = atom<number | null>(null);
export const workspaceLoadingAtom = atom(false);
export const workspaceErrorAtom = atom<string | null>(null);

export const activeWorkspaceAtom = atom((get) => {
  const id = get(activeWorkspaceIdAtom);
  if (!id) return null;
  return get(workspacesAtom).find((w) => w.id === id) ?? null;
});
