const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktopApi", {
  selectOutputPath: (defaultName, ext) => ipcRenderer.invoke("dialog:select-output", defaultName, ext),
  getDefaultOutputPath: (name, ext) => ipcRenderer.invoke("path:default-output", { name, ext }),
  runMerge: (payload) => ipcRenderer.invoke("merge:run", payload),
  showItemInFolder: (targetPath) => ipcRenderer.invoke("shell:show-item", targetPath),
});
