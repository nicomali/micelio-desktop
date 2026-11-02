const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('micelioElectron', {
  pickDirectory: () => ipcRenderer.invoke('micelio:pick-directory'),
});
