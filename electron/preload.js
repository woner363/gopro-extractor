const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Call Python backend methods
  callPython: (method, params) => ipcRenderer.invoke('python:call', method, params),

  // Listen for Python notifications (progress events)
  onPythonNotification: (callback) => {
    const handler = (_event, data) => callback(data);
    ipcRenderer.on('python:notification', handler);
    return () => ipcRenderer.removeListener('python:notification', handler);
  },

  // Open directory picker dialog
  selectDirectory: () => ipcRenderer.invoke('dialog:selectDirectory'),
});
