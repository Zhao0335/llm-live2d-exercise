const { app, BrowserWindow, ipcMain, Menu, Tray, screen } = require('electron');
const path = require('path');

let petWindow = null;
let chatWindow = null;
let tray = null;

// ─── 桌宠窗口 ────────────────────────────────────────────────────────────────
function createPetWindow() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;

  petWindow = new BrowserWindow({
    width: 300,
    height: 400,
    x: sw - 320,
    y: sh - 420,
    transparent: true,
    frame: false,
    backgroundColor: '#00000000',
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });

  petWindow.loadFile(path.join(__dirname, 'pet.html'));

  // 默认开启点击穿透（透明区域点击穿透到下面的窗口）
  // forward: true 保证鼠标移动事件仍然转发给渲染进程（用于判断是否在角色上）
  petWindow.setIgnoreMouseEvents(true, { forward: true });

  petWindow.on('closed', () => { petWindow = null; });
}

// ─── 聊天窗口 ────────────────────────────────────────────────────────────────
function createChatWindow() {
  if (chatWindow) {
    chatWindow.focus();
    return;
  }

  chatWindow = new BrowserWindow({
    width: 1000,
    height: 720,
    alwaysOnTop: true,
    backgroundColor: '#0f1117',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });

  // 直接加载 frontend 的 index.html
  chatWindow.loadFile(path.join(__dirname, '../frontend/public/index.html'));

  chatWindow.on('closed', () => { chatWindow = null; });
}

// ─── IPC ─────────────────────────────────────────────────────────────────────
ipcMain.on('set-ignore-mouse', (_event, ignore) => {
  petWindow?.setIgnoreMouseEvents(ignore, { forward: true });
});

ipcMain.on('open-chat', () => {
  createChatWindow();
});

ipcMain.on('close-window', (event) => {
  BrowserWindow.fromWebContents(event.sender)?.close();
});

// ─── 启动 ────────────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createPetWindow();

  // 系统托盘（图标文件可换成自己的）
  // 如果没有图标文件，跳过托盘创建
  try {
    tray = new Tray(path.join(__dirname, 'assets/tray-icon.png'));
    const menu = Menu.buildFromTemplate([
      { label: '打开聊天', click: createChatWindow },
      { type: 'separator' },
      { label: '退出', click: () => app.quit() },
    ]);
    tray.setToolTip('LLM Live2D');
    tray.setContextMenu(menu);
    tray.on('click', createChatWindow);
  } catch (_) {
    // 无图标文件时静默跳过托盘
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
