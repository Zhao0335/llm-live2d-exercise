# 第 9 章：Live2D 集成

> 这章我们在页面上显示一个 Live2D 虚拟形象，让它在 AI 说话时动嘴，把之前那个纯文字的聊天应用变成一个有"人"在的对话体验。

---

## 9.1 Live2D 是什么，怎么工作

Live2D 是一种 2D 虚拟形象技术。你有一张人物插画，Live2D 会在关键部位（眼睛、嘴巴、头部、身体）设置控制点，通过改变这些点的位置来实现动作——转头、眨眼、动嘴、摇摆。因为都是在 2D 图像上做变形，所以不需要 3D 建模，但效果看起来有立体感。

控制这些动作的是**参数**（Parameters）。每个参数有名字和数值范围，比如：
- `ParamMouthOpenY`：嘴巴开合程度，0 是闭嘴，1 是最大张口
- `ParamEyeBallX`：眼球左右方向，-1 到 1
- `ParamHeadAngleY`：头部上下仰俯

让 AI 说话时嘴巴动，就是实时修改 `ParamMouthOpenY` 的值。

---

## 9.2 技术栈

我们用三个库（都以 script 标签引入，不需要 npm）：

**Live2D Cubism Core**：官方运行时，负责模型文件的解析和参数计算。

**PixiJS**：WebGL 渲染框架，负责把模型画到 canvas 上，性能好。

**pixi-live2d-display**：在 PixiJS 里显示 Live2D 模型的桥接库，把复杂的初始化逻辑封装好了，我们直接用。

从原项目的 `frontend/public/libs/` 文件夹里复制这三个文件到你的 `frontend/libs/`，然后在 HTML 里按顺序引入——顺序不对会出错，必须先 Cubism Core，再 Pixi，再 pixi-live2d-display。

---

## 9.3 获取 Live2D 模型

每个模型是一个文件夹，里面有主配置文件（`.model3.json`）、模型数据（`.moc3`）、贴图（`.png`）和动作/表情文件。

Live2D 官网提供免费示例模型（Hiyori、Haru 等），去 [live2d.com/download/sample-data/](https://www.live2d.com/download/sample-data/) 下载。注意这些模型只能用于学习和非商业项目。

把下载的模型文件夹放到 `frontend/models/` 下面。

---

## 9.4 调整页面布局

加入 Live2D 之后，页面布局要改：左边是 Live2D 的展示区域，右边是聊天面板。

在 HTML 里，加一个 `live2d-container` div 和一个 canvas：

```html
<div class="app">
    <div class="live2d-container" id="live2d-container">
        <canvas id="live2d-canvas"></canvas>
    </div>
    <div class="chat-panel">
        <!-- 聊天界面保持原样 -->
    </div>
</div>
```

CSS 里，`.app` 用 Flexbox 横向排列，`live2d-container` 占 `flex: 1`（剩余宽度），`chat-panel` 固定宽度（约 380px）。背景换成深色（`#1a1a2e`），让 Live2D 模型更好看。

---

## 9.5 Live2DController.js

新建 `frontend/Live2DController.js`，把模型的操作封装成一个类。这样 `main.js` 只需要调用简单的接口，不用关心 Pixi 和 Live2D 的细节。

**初始化**：创建 PixiJS Application，加载模型，设置锚点（底部居中），适配 canvas 大小。

```javascript
async init() {
    this.app = new PIXI.Application({ view: canvas, transparent: true, ... });
    this.model = await PIXI.live2d.Live2DModel.from(this.modelPath);
    this.app.stage.addChild(this.model);
    this.model.anchor.set(0.5, 1.0);  // 锚点在底部中央
    this._fitModel();
}
```

`anchor.set(0.5, 1.0)` 意味着模型的"基准点"在它的底部中央，所以把模型放在 `(容器宽/2, 容器高)` 的位置，模型就会在底部居中显示。

**适配大小**：让模型高度占容器的 90%，水平居中，贴底部。窗口 resize 时重新计算。

**嘴型同步**：这是让说话看起来自然的关键。用 Web Audio API 的 Analyser 节点实时分析音频的频率数据，把音量平均值归一化到 0~1，设为 `ParamMouthOpenY` 的值。平滑处理（新值 = 旧值 × 0.5 + 新值 × 0.5）避免嘴巴抖动。

```javascript
async speak(audioElement) {
    const audioCtx = new AudioContext();
    const source = audioCtx.createMediaElementSource(audioElement);
    const analyser = audioCtx.createAnalyser();
    source.connect(analyser);
    analyser.connect(audioCtx.destination);
    
    const updateMouth = () => {
        analyser.getByteFrequencyData(dataArray);
        const volume = dataArray.slice(0, 32).reduce((a, b) => a + b) / 32;
        this._mouthOpenY = this._mouthOpenY * 0.5 + Math.min(volume / 128, 1) * 0.5;
        if (this._isSpeaking) requestAnimationFrame(updateMouth);
    };
    updateMouth();
}
```

每帧（`requestAnimationFrame`）分析一次音量，更新嘴型参数。音频播放结束时停止更新，嘴巴归零。

**鼠标跟随**：监听 `mousemove`，把鼠标位置转换成 -1~1 的范围，调用 `model.focus(x, y)`，模型的眼睛就会自然地"看向"鼠标。

---

## 9.6 更新 main.js

在 `main.js` 最前面初始化 Live2D：

```javascript
const live2d = new Live2DController(
    "live2d-canvas",
    "./models/Hiyori/Hiyori.model3.json"  // 换成你的模型路径
);

live2d.init().then(success => {
    if (success) {
        live2d.enableMouseTracking();
        live2d.playMotion("Idle");
    }
});
```

然后修改 `playNextAudio` 函数，播放音频时让 Live2D 跟随嘴型：

```javascript
const audio = new Audio(`${API_BASE}${url}`);
audio.crossOrigin = "anonymous";  // Web Audio API 要求这个
const speakPromise = live2d.speak(audio);
await audio.play();
await speakPromise;
```

注意 `audio.crossOrigin = "anonymous"` 很重要——如果没有这个，浏览器的同源策略会阻止 Web Audio API 分析来自不同源的音频。即使是同源的，加上这个也没有副作用。

---

## 9.7 常见问题排查

**模型加载失败**：检查路径是否正确，路径区分大小写。在 Network 面板里看模型文件有没有 404。

**嘴巴不动**：不同的 Live2D 模型，控制嘴巴的参数名可能不同。在 Console 里运行 `live2d.model.internalModel.coreModel._parameterValues` 看一下所有参数名，找到控制嘴型的那个，在 `_tick()` 里改成正确的参数名。

**模型位置/大小不对**：在 `_fitModel()` 里调整 `scale` 的计算方式。

> **试一下**：打开页面，动一动鼠标，看 Live2D 的眼睛有没有跟随。然后发一条消息，听到 AI 说话时，观察嘴巴有没有动。如果都正常，这章就完成了。

---

## 9.8 此时的完整架构

```
用户说话（麦克风）
    ↓
Web Speech API / Whisper → 文字 → WebSocket 发出
    ↓
后端：LLM 流式生成
    ↓ 每个 Token
前端：文字追加到气泡 + Live2D 待机
    ↓ 每个完整句子
后端：TTS 合成 → 发回 audio URL
    ↓
前端：播放音频 + Live2D 嘴型同步
```

从用户角度：说话 → 文字显示 → 听到 AI 回复 + 看到嘴巴动。基本上和面对面对话差不多的流畅感。

---

## 本章小结

- Live2D 通过修改参数值（如 `ParamMouthOpenY`）控制模型动作
- PixiJS + pixi-live2d-display：加载模型、渲染、适配大小
- Web Audio API 的 Analyser 节点：实时分析音量 → 驱动嘴型参数
- `requestAnimationFrame` 每帧更新嘴型，`× 0.5` 平滑避免抖动
- `audio.crossOrigin = "anonymous"` 是 Web Audio API 分析外部音频的必要属性

---

→ 下一章：[第 10 章：表情与动作系统](10-表情与动作系统.md)
