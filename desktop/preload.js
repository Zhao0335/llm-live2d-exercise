const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  openChat:      ()        => ipcRenderer.send('open-chat'),
  closeWindow:   ()        => ipcRenderer.send('close-window'),
  setIgnoreMouse:(ignore)  => ipcRenderer.send('set-ignore-mouse', ignore),
});
