const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("projectR", {
  platform: process.platform,
  window: {
    minimize: () => ipcRenderer.invoke("window:minimize"),
    toggleMaximize: () => ipcRenderer.invoke("window:toggle-maximize"),
    close: () => ipcRenderer.invoke("window:close"),
    isMaximized: () => ipcRenderer.invoke("window:is-maximized"),
    onStateChange: (callback) => {
      const handler = (_event, state) => callback(state);
      ipcRenderer.on("window:state", handler);
      return () => ipcRenderer.removeListener("window:state", handler);
    },
  },
  prompts: {
    listUser: () => ipcRenderer.invoke("prompts:list-user"),
    saveUser: (input) => ipcRenderer.invoke("prompts:save-user", input),
    deleteUser: (id) => ipcRenderer.invoke("prompts:delete-user", id),
  },
  updates: {
    getCurrentVersion: () => ipcRenderer.invoke("updates:get-current-version"),
    download: (input) => ipcRenderer.invoke("updates:download", input),
    install: (input) => ipcRenderer.invoke("updates:install", input),
    onProgress: (callback) => {
      const handler = (_event, progress) => callback(progress);
      ipcRenderer.on("updates:progress", handler);
      return () => ipcRenderer.removeListener("updates:progress", handler);
    },
  },
});
