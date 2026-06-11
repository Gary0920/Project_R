import { atom } from "jotai";

export type Tab = {
  id: string;
  sessionId: number | null;
  workspaceId: number | null;
  title: string;
};

export const tabsAtom = atom<Tab[]>([]);
export const activeTabIdAtom = atom<string>("");

export const activeTabAtom = atom((get) => {
  const id = get(activeTabIdAtom);
  return get(tabsAtom).find((t) => t.id === id) ?? null;
});
