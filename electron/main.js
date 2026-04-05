const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { PythonBridge } = require('./python-bridge');

let mainWindow;
let pythonBridge;

const isDev = !app.isPackaged;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 700,
    minWidth: 640,
    minHeight: 560,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 16 },
    backgroundColor: '#f8fafc',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

function setupPythonBridge() {
  let pythonExe, backendDir, configPath;

  if (isDev) {
    // Development: use venv Python + source files
    backendDir = path.join(__dirname, '../backend');
    pythonExe = path.join(__dirname, '../.venv/bin/python3');
    configPath = path.join(__dirname, '../config/default.yaml');
  } else {
    // Production: use PyInstaller-bundled executable
    const resourcesDir = process.resourcesPath;
    backendDir = path.join(resourcesDir, 'pybackend', 'gopro-backend');
    pythonExe = path.join(backendDir, 'gopro-backend');
    configPath = path.join(resourcesDir, 'config', 'default.yaml');
  }

  pythonBridge = new PythonBridge(pythonExe, backendDir, configPath);

  pythonBridge.on('notification', (method, params) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('python:notification', { method, params });
    }
  });

  pythonBridge.on('error', (err) => {
    console.error('Python bridge error:', err);
  });

  pythonBridge.start();
}

// IPC Handlers
ipcMain.handle('python:call', async (_event, method, params) => {
  if (!pythonBridge) {
    return { error: 'Python backend not started' };
  }
  try {
    return await pythonBridge.call(method, params || {});
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('dialog:selectDirectory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select NAS Mount Path',
  });
  return result.canceled ? null : result.filePaths[0];
});

app.whenReady().then(() => {
  setupPythonBridge();
  createWindow();
});

app.on('window-all-closed', () => {
  if (pythonBridge) pythonBridge.stop();
  app.quit();
});

app.on('before-quit', () => {
  if (pythonBridge) pythonBridge.stop();
});
