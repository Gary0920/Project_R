import { app, BrowserWindow, Menu, ipcMain, screen, shell, dialog } from "electron";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  downloadUpdatePackageToFile,
  type UpdateDownloadInput as UpdateDownloadJobInput,
  type UpdateProgress,
} from "./update-download.js";
import { createPrivateWorkspaceService, type PrivateWorkspaceFileRecord } from "./private-workspace.js";

type WindowState = {
  width: number;
  height: number;
  x?: number;
  y?: number;
};

type UserPrompt = {
  id: string;
  name: string;
  content: string;
  createdAt: string;
  updatedAt: string;
};

type DevToolsShortcutInput = {
  key: string;
  control?: boolean;
  meta?: boolean;
  shift?: boolean;
};

type UpdateDownloadInput = Omit<UpdateDownloadJobInput, "downloadsDir">;

type UpdateInstallInput = {
  filePath: string;
  version?: string;
  dryRun?: boolean;
};

const DEFAULT_WINDOW_STATE: WindowState = {
  width: 1400,
  height: 900,
};

const __dirname = dirname(fileURLToPath(import.meta.url));
let mainWindow: BrowserWindow | null = null;

app.commandLine.appendSwitch("proxy-bypass-list", "<-loopback>;localhost;127.0.0.1;::1");

function getWindowIconPath() {
  const candidates = [
    join(__dirname, "../../resources/project-r.ico"),
    join(process.cwd(), "resources", "project-r.ico"),
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function getMainWindow() {
  return mainWindow && !mainWindow.isDestroyed() ? mainWindow : BrowserWindow.getFocusedWindow();
}

function sendWindowState() {
  const window = getMainWindow();
  if (!window || window.isDestroyed()) {
    return;
  }
  window.webContents.send("window:state", { isMaximized: window.isMaximized() });
}

function getWindowStatePath() {
  return join(app.getPath("userData"), "window-state.json");
}

function getUserPromptsPath() {
  return join(app.getPath("userData"), "prompts", "user-prompts.json");
}

function getUpdateDownloadsDir() {
  return join(app.getPath("userData"), "updates");
}

function getPrivateWorkspaceService() {
  return createPrivateWorkspaceService({
    userDataDir: app.getPath("userData"),
    documentsDir: app.getPath("documents"),
  });
}

function readUserPrompts(): UserPrompt[] {
  const promptsPath = getUserPromptsPath();
  if (!existsSync(promptsPath)) {
    return [];
  }
  try {
    const parsed = JSON.parse(readFileSync(promptsPath, "utf-8")) as UserPrompt[];
    return parsed.filter((item) => item.id && item.name && item.content);
  } catch {
    return [];
  }
}

function writeUserPrompts(prompts: UserPrompt[]) {
  const promptsPath = getUserPromptsPath();
  mkdirSync(dirname(promptsPath), { recursive: true });
  writeFileSync(promptsPath, JSON.stringify(prompts, null, 2), "utf-8");
}

function emitUpdateProgress(sender: Electron.WebContents, progress: UpdateProgress) {
  if (!sender.isDestroyed()) {
    sender.send("updates:progress", progress);
  }
}

async function installDownloadedUpdate(input: UpdateInstallInput, sender?: Electron.WebContents) {
  const filePath = input.filePath?.trim();
  if (!filePath || !existsSync(filePath)) {
    throw new Error("安装包不存在");
  }
  const version = input.version ?? "";
  const emitInstallProgress = (message: string) => {
    if (!sender || sender.isDestroyed()) return;
    sender.send("updates:progress", {
      version,
      status: "installing",
      receivedBytes: 0,
      totalBytes: 0,
      percent: 100,
      bytesPerSecond: 0,
      filePath,
      message,
      dryRun: Boolean(input.dryRun),
    } satisfies UpdateProgress);
  };
  if (input.dryRun) {
    emitInstallProgress("dry-run: 静默安装与重启已模拟");
    return { ok: true, dryRun: true };
  }
  emitInstallProgress("正在静默安装更新，完成后会自动重启应用...");
  const child = spawn(filePath, ["/S", "--force-run"], {
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  child.on("error", (error) => {
    if (sender && !sender.isDestroyed()) {
      sender.send("updates:progress", {
        version,
        status: "error",
        receivedBytes: 0,
        totalBytes: 0,
        percent: 0,
        bytesPerSecond: 0,
        filePath,
        message: error.message || "静默安装启动失败",
        dryRun: false,
      } satisfies UpdateProgress);
    }
  });
  child.unref();
  setTimeout(() => app.quit(), 800);
  return { ok: true, dryRun: false };
}

function saveUserPrompt(input: { id?: string; name?: string; content?: string }) {
  const name = input.name?.trim() ?? "";
  const content = input.content?.trim() ?? "";
  if (!name || !content) {
    throw new Error("提示词名称和内容不能为空");
  }
  const prompts = readUserPrompts();
  const now = new Date().toISOString();
  const id = input.id || `user-${Date.now()}`;
  const existing = prompts.find((item) => item.id === id);
  const nextPrompt: UserPrompt = {
    id,
    name: name.slice(0, 80),
    content,
    createdAt: existing?.createdAt ?? now,
    updatedAt: now,
  };
  const next = existing
    ? prompts.map((item) => item.id === id ? nextPrompt : item)
    : [nextPrompt, ...prompts];
  writeUserPrompts(next);
  return nextPrompt;
}

function readWindowState(): WindowState {
  const statePath = getWindowStatePath();
  if (!existsSync(statePath)) {
    return DEFAULT_WINDOW_STATE;
  }

  try {
    const parsed = JSON.parse(readFileSync(statePath, "utf-8")) as WindowState;
    return {
      width: Math.max(parsed.width || DEFAULT_WINDOW_STATE.width, 800),
      height: Math.max(parsed.height || DEFAULT_WINDOW_STATE.height, 600),
      x: parsed.x,
      y: parsed.y,
    };
  } catch {
    return DEFAULT_WINDOW_STATE;
  }
}

function saveWindowState(window: BrowserWindow) {
  if (window.isDestroyed()) {
    return;
  }

  const bounds = window.getBounds();
  writeFileSync(getWindowStatePath(), JSON.stringify(bounds, null, 2), "utf-8");
}

function ensureVisibleState(state: WindowState): WindowState {
  if (state.x === undefined || state.y === undefined) {
    return state;
  }

  const displays = screen.getAllDisplays();
  const visible = displays.some((display) => {
    const bounds = display.workArea;
    return (
      state.x !== undefined &&
      state.y !== undefined &&
      state.x >= bounds.x &&
      state.y >= bounds.y &&
      state.x < bounds.x + bounds.width &&
      state.y < bounds.y + bounds.height
    );
  });

  return visible ? state : DEFAULT_WINDOW_STATE;
}

function isDevToolsShortcut(input: DevToolsShortcutInput) {
  const key = input.key.toLowerCase();
  return key === "f12" || ((input.control || input.meta) && input.shift && key === "i");
}

function toggleDevTools(window: BrowserWindow) {
  if (window.webContents.isDevToolsOpened()) {
    window.webContents.closeDevTools();
    return;
  }
  window.webContents.openDevTools({ mode: "detach" });
}

function sleep(ms: number) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

async function loadDevServerUrl(window: BrowserWindow, url: string) {
  let lastError: unknown;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      await window.loadURL(url);
      return;
    } catch (error) {
      lastError = error;
      await sleep(150);
    }
  }
  throw lastError;
}

async function createWindow() {
  Menu.setApplicationMenu(null);
  const state = ensureVisibleState(readWindowState());
  mainWindow = new BrowserWindow({
    width: state.width,
    height: state.height,
    x: state.x,
    y: state.y,
    minWidth: 800,
    minHeight: 600,
    title: "Project_R",
    frame: process.platform === "darwin",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "hidden",
    backgroundColor: "#f7f6f1",
    icon: getWindowIconPath(),
    webPreferences: {
      preload: process.env.PROJECT_R_PRELOAD_PATH || join(__dirname, "../preload/preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const currentWindow = mainWindow;
  currentWindow.webContents.on("before-input-event", (event, input) => {
    if (!isDevToolsShortcut(input)) {
      return;
    }
    event.preventDefault();
    toggleDevTools(currentWindow);
  });
  currentWindow.on("close", () => saveWindowState(currentWindow));
  currentWindow.on("closed", () => {
    if (mainWindow === currentWindow) {
      mainWindow = null;
    }
  });
  mainWindow.on("maximize", sendWindowState);
  mainWindow.on("unmaximize", sendWindowState);
  mainWindow.on("restore", sendWindowState);

  if (process.env.VITE_DEV_SERVER_URL) {
    await loadDevServerUrl(mainWindow, process.env.VITE_DEV_SERVER_URL);
  } else {
    await mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

app.whenReady().then(() => {
  ipcMain.handle("window:minimize", () => {
    getMainWindow()?.minimize();
  });
  ipcMain.handle("window:toggle-maximize", () => {
    const window = getMainWindow();
    if (!window) return false;
    if (window.isMaximized()) {
      window.unmaximize();
    } else {
      window.maximize();
    }
    return window.isMaximized();
  });
  ipcMain.handle("window:close", () => {
    getMainWindow()?.close();
  });
  ipcMain.handle("window:is-maximized", () => Boolean(getMainWindow()?.isMaximized()));
  ipcMain.handle("prompts:list-user", () => readUserPrompts());
  ipcMain.handle("prompts:save-user", (_event, input: { id?: string; name?: string; content?: string }) => saveUserPrompt(input ?? {}));
  ipcMain.handle("prompts:delete-user", (_event, id: string) => {
    const prompts = readUserPrompts().filter((item) => item.id !== id);
    writeUserPrompts(prompts);
    return prompts;
  });
  ipcMain.handle("private-workspace:get-config", () => getPrivateWorkspaceService().readConfig());
  ipcMain.handle("private-workspace:get-worker-status", () => getPrivateWorkspaceService().getWorkerStatus());
  ipcMain.handle("private-workspace:choose-root", async () => {
    const service = getPrivateWorkspaceService();
    const current = service.readConfig();
    const options: Electron.OpenDialogOptions = {
      title: "选择 Project_R 本机文件处理目录",
      defaultPath: current.rootPath,
      properties: ["openDirectory", "createDirectory"],
    };
    const window = getMainWindow();
    const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
    if (result.canceled || !result.filePaths[0]) {
      return current;
    }
    return service.setRoot(result.filePaths[0]);
  });
  ipcMain.handle("private-workspace:open-root", async () => {
    const config = getPrivateWorkspaceService().readConfig();
    const errorMessage = await shell.openPath(config.rootPath);
    if (errorMessage) {
      throw new Error(errorMessage);
    }
    return config;
  });
  ipcMain.handle("private-workspace:reset-root", () => {
    const service = getPrivateWorkspaceService();
    return service.setRoot(service.getDefaultRoot());
  });
  ipcMain.handle("private-workspace:get-manifest", () => getPrivateWorkspaceService().readManifest());
  ipcMain.handle("private-workspace:quick-drop", async () => {
    const options: Electron.OpenDialogOptions = {
      title: "快速添加本机文件到 Project_R",
      properties: ["openFile", "multiSelections"],
    };
    const window = getMainWindow();
    const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
    if (result.canceled || !result.filePaths.length) {
      return { records: getPrivateWorkspaceService().readManifest(), added: [] };
    }
    const service = getPrivateWorkspaceService();
    const added = service.copyFilesToInbox(result.filePaths);
    return { records: service.readManifest(), added };
  });
  ipcMain.handle("private-workspace:choose-files", async () => {
    const service = getPrivateWorkspaceService();
    const options: Electron.OpenDialogOptions = {
      title: "选择本机文件添加到对话",
      properties: ["openFile", "multiSelections"],
    };
    const window = getMainWindow();
    const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
    if (result.canceled || !result.filePaths.length) {
      return [];
    }
    return service.readFilePayloads(result.filePaths);
  });
  ipcMain.handle("private-workspace:set-authorization", (_event, input: { ids?: string[]; status?: PrivateWorkspaceFileRecord["lastAuthorizationStatus"] }) => {
    const ids = Array.isArray(input?.ids) ? input.ids.filter((item): item is string => typeof item === "string") : [];
    const status = input?.status === "uploaded" || input?.status === "authorized" ? input.status : "pending";
    return getPrivateWorkspaceService().setAuthorization(ids, status);
  });
  ipcMain.handle("updates:get-current-version", () => app.getVersion());
  ipcMain.handle("updates:download", async (event, input: UpdateDownloadInput) => {
    const payload = (input ?? {}) as UpdateDownloadInput;
    try {
      return await downloadUpdatePackageToFile(
        { ...payload, downloadsDir: getUpdateDownloadsDir() },
        (progress) => emitUpdateProgress(event.sender, progress),
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "自动更新失败";
      emitUpdateProgress(event.sender, {
        version: payload.version ?? "",
        status: "error",
        receivedBytes: 0,
        totalBytes: 0,
        percent: 0,
        bytesPerSecond: 0,
        message,
        dryRun: Boolean(payload.dryRun),
      });
      return { ok: false, message };
    }
  });
  ipcMain.handle("updates:install", async (event, input: UpdateInstallInput) => {
    const payload = (input ?? {}) as UpdateInstallInput;
    try {
      return await installDownloadedUpdate(payload, event.sender);
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : "启动安装器失败" };
    }
  });

  void createWindow().catch((error: unknown) => {
    console.error("Failed to create Project_R window:", error);
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void createWindow().catch((error: unknown) => {
      console.error("Failed to recreate Project_R window:", error);
    });
  }
});
