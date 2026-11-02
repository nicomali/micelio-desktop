/**
 * Electron Main Process (`electron/main.cjs`).
 * Automatically spawns the Python FastAPI Core Engine (`python -m engine.main`)
 * if it is not already listening on port 8765, and opens the Micelio Desktop window.
 */

const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

let mainWindow = null;
let pythonProcess = null;
const ENGINE_PORT = process.env.MICELIO_ENGINE_PORT || 8765;

function checkEngineAlive() {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${ENGINE_PORT}/api/health`, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function ensurePythonEngine() {
  const alive = await checkEngineAlive();
  if (alive) {
    return;
  }
  const repoRoot = path.resolve(__dirname, '..');
  pythonProcess = spawn('python', ['-m', 'engine.main'], {
    cwd: repoRoot,
    env: { ...process.env, MICELIO_ENGINE_PORT: String(ENGINE_PORT) },
    stdio: 'inherit',
  });

  // Poll /api/health until the FastAPI server is ready to accept requests
  for (let attempt = 0; attempt < 30; attempt++) {
    const ready = await checkEngineAlive();
    if (ready) {
      return;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
}

async function createWindow() {
  await ensurePythonEngine();

  const iconPath =
    process.platform === 'win32'
      ? path.join(__dirname, '..', 'public', 'icon.ico')
      : path.join(__dirname, '..', 'public', 'icon.png');

  mainWindow = new BrowserWindow({
    width: 1520,
    height: 940,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: '#09090B',
    title: 'Micelio — Santander Engineering Harness',
    icon: iconPath,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
  const distIndex = path.join(__dirname, '..', 'dist', 'index.html');

  // Try Vite dev server first; fall back to built dist/index.html
  http
    .get(devUrl, () => {
      mainWindow.loadURL(devUrl);
    })
    .on('error', () => {
      mainWindow.loadFile(distIndex);
    });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

ipcMain.handle('micelio:pick-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
  });
  if (result.canceled || !result.filePaths.length) {
    return null;
  }
  return result.filePaths[0];
});

app.whenReady().then(createWindow);

function stopPythonEngine() {
  if (!pythonProcess || !pythonProcess.pid) {
    return;
  }
  const pid = pythonProcess.pid;
  pythonProcess = null;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
    } else {
      process.kill(pid, 'SIGTERM');
    }
  } catch (_) {}
}

app.on('before-quit', () => {
  stopPythonEngine();
});

app.on('window-all-closed', () => {
  stopPythonEngine();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
