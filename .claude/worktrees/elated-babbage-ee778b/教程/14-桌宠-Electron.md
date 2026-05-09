# 第 14 章：桌宠 —— 用 Electron 把 AI 放到桌面上

> 这章把我们的 Live2D AI 助手从浏览器搬到桌面——透明背景、始终置顶、点击穿透、右下角常驻，点击角色弹出聊天窗口，就像一个真正的桌面宠物。

---

## 14.1 效果目标

打开应用，Live2D 角色站在桌面右下角。你在用 VSCode 写代码，它就在旁边陪着你。点一下角色，旁边弹出聊天窗口，你可以问 AI 问题。关掉聊天窗口，角色继续待着。

实现这个需要几个特性：
- **透明背景**：窗口背景完全透明，只有角色可见
- **无边框**：没有系统的标题栏和边框
- **始终置顶**：覆盖在其他窗口上面
- **点击穿透**：透明区域的点击"穿过"应用，落到下面的窗口

---

## 14.2 Electron 是什么

**Electron** 把 Node.js 和 Chromium 打包在一起，让你用 HTML/CSS/JavaScript 写桌面应用。我们前几章写的前端代码可以直接复用——不需要学新语言。

Electron 应用有两类进程：

**主进程（Main Process）**：`main.js`，Node.js 环境，控制窗口的创建、系统托盘、IPC 通信。只有主进程能直接操作操作系统的 API。

**渲染进程（Renderer Process）**：每个窗口是一个渲染进程，就是一个 Chromium 浏览器页面，运行你写的 HTML/CSS/JS。

两个进程之间用 **IPC（进程间通信）** 交流：渲染进程通过 `preload.js` 暴露出来的安全桥接，发消息给主进程，主进程响应。

---

## 14.3 项目结构

在 `my-live2d/` 下新建 `desktop/` 文件夹：

```
desktop/
├── package.json          ← 项目配置，声明 Electron 依赖
├── main.js               ← 主进程：控制窗口
├── preload.js            ← 安全桥接：暴露 IPC 给渲染进程
├── pet.html              ← 桌宠窗口（Live2D 角色）
├── chat.html             ← 聊天窗口（复用前端逻辑）
└── assets/
    └── tray-icon.png     ← 托盘图标（32x32 PNG）
```

初始化：

```bash
cd desktop
npm init -y
npm install --save-dev electron electron-builder
```

在 `package.json` 里加 `"main": "main.js"` 和启动脚本：

```json
"scripts": {
    "start": "electron .",
    "build:win": "electron-builder --win",
    "build:mac": "electron-builder --mac"
}
```

---

## 14.4 主进程：main.js

主进程负责创建和管理两个窗口：**桌宠窗口**（Live2D 角色）和**聊天窗口**（聊天界面）。

**桌宠窗口**的关键配置：

```javascript
petWindow = new BrowserWindow({
    transparent: true,          // 透明背景
    frame: false,               // 无边框
    backgroundColor: "#00000000",
    alwaysOnTop: true,          // 始终置顶
    skipTaskbar: true,          // 不出现在任务栏
    webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
    },
});

petWindow.setIgnoreMouseEvents(true, { forward: true });
```

`setIgnoreMouseEvents(true, { forward: true})` 是点击穿透的关键：开启了就忽略鼠标事件（点击会穿透到下面的窗口），`forward: true` 的意思是把鼠标移动事件继续转发给渲染进程（这样 `mousemove` 还能触发，用来检测鼠标在不在角色上面）。

**如何让角色本体可点击，透明区域穿透**：渲染进程监听 `mousemove`，判断当前鼠标所在的像素是不是透明的。如果是透明像素，通过 IPC 告诉主进程"继续穿透"；如果是角色本体（不透明），告诉主进程"关闭穿透，我要响应点击了"。

```javascript
// main.js 里监听渲染进程发来的消息
ipcMain.on("set-ignore-mouse", (event, ignore) => {
    petWindow?.setIgnoreMouseEvents(ignore, { forward: true });
});
```

**聊天窗口**：点击角色时创建，关闭时销毁。如果已经存在就把它移到前台：

```javascript
function createChatWindow() {
    if (chatWindow) { chatWindow.focus(); return; }
    chatWindow = new BrowserWindow({
        frame: false,
        alwaysOnTop: true,
        ...
    });
    chatWindow.loadFile("chat.html");
    chatWindow.on("closed", () => { chatWindow = null; });
}
```

**系统托盘**：在任务栏旁边显示一个小图标，右键显示菜单（打开聊天、退出等）：

```javascript
tray = new Tray(path.join(__dirname, "assets/tray-icon.png"));
const menu = Menu.buildFromTemplate([
    { label: "打开聊天", click: createChatWindow },
    { label: "退出", click: () => app.quit() },
]);
tray.setContextMenu(menu);
tray.on("click", createChatWindow);
```

---

## 14.5 preload.js：安全桥接

渲染进程里的 JS（你的前端代码）不能直接调用 Node.js API——这是安全设计。`preload.js` 运行在特殊的中间层，可以同时访问 Node.js 和浏览器 API，用 `contextBridge` 把有限的功能安全地暴露给渲染进程：

```javascript
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
    // 渲染进程可以调用这些
    openChat: () => ipcRenderer.send("open-chat"),
    closeWindow: () => ipcRenderer.send("close-window"),
    setIgnoreMouse: (ignore) => ipcRenderer.send("set-ignore-mouse", ignore),
    dragWindow: () => ipcRenderer.send("drag-window"),
});
```

然后在渲染进程里就可以：

```javascript
window.electronAPI.openChat();  // 发消息给主进程，让它打开聊天窗口
```

---

## 14.6 pet.html：桌宠页面

这个页面只显示 Live2D 角色，背景完全透明，没有聊天界面。

**点击穿透逻辑**：监听 `mousemove`，用 `document.elementFromPoint(x, y)` 找到鼠标下面的元素，再判断那个位置是否透明（用 canvas getImageData 采样像素的 alpha 值）。如果 alpha < 10，说明是透明区域，开启穿透；否则关闭穿透。

```javascript
document.addEventListener("mousemove", (e) => {
    // 简化：检测鼠标是否在 canvas 上的不透明像素
    const isOnModel = isHoveringModel(e.clientX, e.clientY);
    window.electronAPI.setIgnoreMouse(!isOnModel);
    
    if (isOnModel) {
        document.body.style.cursor = "pointer";
    }
});
```

点击角色时打开聊天窗口：

```javascript
document.addEventListener("click", () => {
    window.electronAPI.openChat();
});
```

**窗口拖动**：在 CSS 里把非交互区域设置为可拖动（`-webkit-app-region: drag`），角色本体设置为不可拖动（`-webkit-app-region: no-drag`），这样拖动角色旁边的透明区域就能移动窗口。

---

## 14.7 chat.html：聊天窗口

这个窗口复用之前写的聊天界面逻辑。因为是 `frame: false`（无边框），需要自己做标题栏——一个横条，上面有关闭按钮：

```html
<div class="title-bar" style="-webkit-app-region: drag">
    <span>AI 助手</span>
    <button onclick="window.electronAPI.closeWindow()" style="-webkit-app-region: no-drag">✕</button>
</div>
```

`-webkit-app-region: drag` 让整个标题栏可以拖动窗口，按钮设置 `no-drag` 防止点按钮时触发拖动。

---

## 14.8 可选：让 Electron 自动启动后端

现在 Electron 打开时，后端需要单独手动启动。可以让主进程在启动时自动启动 Python 后端：

```javascript
const { spawn } = require("child_process");

let backendProcess = null;

function startBackend() {
    backendProcess = spawn("python", ["-m", "uvicorn", "main:app", "--port", "8000"], {
        cwd: path.join(__dirname, "../backend"),
    });
    backendProcess.stdout.on("data", (data) => console.log("后端:", data.toString()));
    backendProcess.stderr.on("data", (data) => console.error("后端错误:", data.toString()));
}

app.whenReady().then(() => {
    startBackend();
    setTimeout(createPetWindow, 1500);  // 等后端启动
});

app.on("will-quit", () => {
    backendProcess?.kill();
});
```

等 1.5 秒再创建窗口，给后端一点启动时间。更健壮的做法是轮询 `/api/health` 接口，确认后端就绪再继续。

---

## 14.9 打包成安装程序

开发完成后，用 electron-builder 打包：

```bash
# Windows 打包成 .exe 安装程序
npm run build:win

# Mac 打包成 .dmg
npm run build:mac
```

打包后的文件在 `dist/` 文件夹里。Windows 用户双击 `.exe` 就能安装，Mac 用户拖到 Applications 文件夹。

> **试一下**：先用 `npm start` 在开发模式下跑起来，确认桌宠窗口出现、透明背景正常、点击穿透生效、聊天窗口能打开。没问题再打包。

---

## 本章小结

- Electron = Node.js + Chromium，前端代码直接复用
- `transparent + frame: false + alwaysOnTop + skipTaskbar`：桌宠窗口的四件套
- `setIgnoreMouseEvents(true, { forward: true })`：透明区域点击穿透，但鼠标移动事件继续转发
- `preload.js + contextBridge`：安全桥接，把有限的 IPC 能力暴露给渲染进程
- `-webkit-app-region: drag / no-drag`：无边框窗口的自定义拖动区域
- `child_process.spawn` 可以在 Electron 里自动启动 Python 后端

