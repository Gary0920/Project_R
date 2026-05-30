import { atom } from "jotai";

export const activeModeAtom = atom<"chat" | "agent">("chat");
