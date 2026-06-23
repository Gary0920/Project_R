const SIDEBAR_WIDTH_KEY = "project-r:chat-sidebar-width";
const SIDEBAR_COLLAPSED_KEY = "project-r:chat-sidebar-collapsed";
const SIDEBAR_MIN_WIDTH = 220;
export const SIDEBAR_COLLAPSED_WIDTH = 56;
const SIDEBAR_DEFAULT_WIDTH = 268;
const SIDEBAR_MAX_WIDTH = 420;

const WORKSPACE_PANEL_WIDTH_KEY = "project-r:workspace-panel-width";
const WORKSPACE_PANEL_MIN_WIDTH = 320;
export const WORKSPACE_PANEL_DEFAULT_WIDTH = 480;
export const WORKSPACE_PANEL_PREVIEW_WIDTH = 720;
const WORKSPACE_PANEL_MAX_WIDTH = 880;

const AUXILIARY_PANEL_WIDTH_KEY = "project-r:auxiliary-side-panel-width";
const AUXILIARY_PANEL_MIN_WIDTH = 300;
const AUXILIARY_PANEL_DEFAULT_WIDTH = 380;
const AUXILIARY_PANEL_MAX_WIDTH = 720;

function sidebarMaxWidth() {
  if (typeof window === "undefined") return SIDEBAR_MAX_WIDTH;
  return Math.max(SIDEBAR_MIN_WIDTH, Math.min(SIDEBAR_MAX_WIDTH, window.innerWidth - 640));
}

export function clampSidebarWidth(value: number) {
  return Math.min(sidebarMaxWidth(), Math.max(SIDEBAR_MIN_WIDTH, Math.round(value)));
}

export function readSidebarWidth() {
  try {
    const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY));
    return Number.isFinite(stored) ? clampSidebarWidth(stored) : SIDEBAR_DEFAULT_WIDTH;
  } catch {
    return SIDEBAR_DEFAULT_WIDTH;
  }
}

export function writeSidebarWidth(width: number) {
  try {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

export function readSidebarCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  } catch {
    return false;
  }
}

export function writeSidebarCollapsed(collapsed: boolean) {
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "true" : "false");
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

export function workspacePanelMaxWidth() {
  if (typeof window === "undefined") return WORKSPACE_PANEL_MAX_WIDTH;
  return Math.max(WORKSPACE_PANEL_MIN_WIDTH, Math.min(WORKSPACE_PANEL_MAX_WIDTH, window.innerWidth - 420));
}

export function clampWorkspacePanelWidth(value: number) {
  return Math.min(workspacePanelMaxWidth(), Math.max(WORKSPACE_PANEL_MIN_WIDTH, Math.round(value)));
}

export function readWorkspacePanelWidth() {
  try {
    const stored = Number(localStorage.getItem(WORKSPACE_PANEL_WIDTH_KEY));
    return Number.isFinite(stored) ? clampWorkspacePanelWidth(stored) : clampWorkspacePanelWidth(WORKSPACE_PANEL_DEFAULT_WIDTH);
  } catch {
    return clampWorkspacePanelWidth(WORKSPACE_PANEL_DEFAULT_WIDTH);
  }
}

export function writeWorkspacePanelWidth(width: number) {
  try {
    localStorage.setItem(WORKSPACE_PANEL_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}

export function auxiliaryPanelMaxWidth() {
  if (typeof window === "undefined") return AUXILIARY_PANEL_MAX_WIDTH;
  return Math.max(AUXILIARY_PANEL_MIN_WIDTH, Math.min(AUXILIARY_PANEL_MAX_WIDTH, window.innerWidth - 420));
}

export function clampAuxiliaryPanelWidth(value: number) {
  return Math.min(auxiliaryPanelMaxWidth(), Math.max(AUXILIARY_PANEL_MIN_WIDTH, Math.round(value)));
}

export function readAuxiliaryPanelWidth() {
  try {
    const stored = Number(localStorage.getItem(AUXILIARY_PANEL_WIDTH_KEY));
    return Number.isFinite(stored) ? clampAuxiliaryPanelWidth(stored) : clampAuxiliaryPanelWidth(AUXILIARY_PANEL_DEFAULT_WIDTH);
  } catch {
    return clampAuxiliaryPanelWidth(AUXILIARY_PANEL_DEFAULT_WIDTH);
  }
}

export function writeAuxiliaryPanelWidth(width: number) {
  try {
    localStorage.setItem(AUXILIARY_PANEL_WIDTH_KEY, String(width));
  } catch {
    // localStorage may be unavailable in restricted shells.
  }
}
