# 第 2 章：前端基础 —— HTML、CSS、JavaScript

> 上一章我们装好了工具，跑起来了两个孤立的 Hello World。这章我们专门做前端——写出一个长得像样的聊天界面，让它能接受输入、显示消息、有等待动画。虽然现在还连不上后端，但界面的逻辑已经是完整的了。

---

## 2.1 三件套的分工

打开任何一个网页，右键查看源码，你看到的就是 HTML。浏览器读到这些标签，知道"这里是一个输入框、那里是一个按钮"，这就是 **HTML 的职责：定义结构和内容**。

但是一堆没有样式的标签，看起来很丑——黑字白底，按钮毫无美感。**CSS 的职责**就是化妆：这个按钮是什么颜色、消息气泡有多少圆角、页面背景是什么渐变。

最后，用户点了发送按钮，页面要有反应——这就是 **JavaScript 的职责**：监听事件，操作页面内容，发 HTTP 请求，把响应展示出来。

三者一起工作：HTML 是骨架，CSS 是皮肤，JavaScript 是肌肉。

---

## 2.2 HTML：写聊天界面的骨架

每个 HTML 文件的结构都是固定的：`<!DOCTYPE html>` 声明文档类型，`<html>` 是根元素，`<head>` 放配置信息（不显示在页面上），`<body>` 放页面内容。

我们的聊天界面需要三块：
1. **顶部标题栏**——显示应用名称和连接状态
2. **消息区域**——显示对话历史，内容超出时可以滚动
3. **底部输入区**——输入框加发送按钮

在 HTML 里，`div` 是最常用的容器标签，本身没有特殊含义，靠 `class` 属性来区分用途。`class` 是给 CSS 和 JavaScript 识别元素用的标签，一个元素可以有多个 class，用空格分隔。

> **你可能会问**：为什么不直接用有语义的标签，比如 `<section>` 或 `<article>`？
>
> 在聊天界面这种动态应用里，语义化标签帮助不大——重要的是 JavaScript 能快速找到你想操作的元素。`div + class` 的组合已经够用，别过度设计。

消息区域是整个界面里最关键的部分。它需要 `overflow-y: auto`（内容超出时出现竖向滚动条）和 `flex: 1`（占满父容器剩余的高度）。这两个属性配合，就能做出消息区域可以独立滚动的效果。

---

## 2.3 CSS：让界面好看

CSS 的基本语法是：**选择器 + 花括号 + 属性列表**。

选择器告诉浏览器"我要给哪些元素加样式"：
- `body` 选到 body 标签
- `.message` 选到所有 `class="message"` 的元素（注意有个点）
- `#send-btn` 选到 `id="send-btn"` 的元素（注意有个 `#`）

聊天界面的布局，我们用 **Flexbox**。父元素设置 `display: flex; flex-direction: column`，子元素就会竖向排列。消息区域设置 `flex: 1`，就会自动占满父容器的剩余高度——这样无论窗口有多高，输入框永远在底部，消息区域永远占满中间。

消息气泡有两种：用户发的和 AI 回的。用户消息靠右（`align-self: flex-end`），AI 消息靠左（`align-self: flex-start`）。颜色上，用户用主题色，AI 用浅灰色——这个设计来自几乎所有聊天应用，用户一眼就能分清谁说的什么。

**"正在思考"动画**是三个小圆点在跳。实现原理：三个 `<span>` 各加一个 CSS `animation`，用 `animation-delay` 让它们依次开始，就有了波浪感。

> **试一下**：写好 CSS 后，在 HTML 里先手动放几条不同 class 的消息（一条 `message user`，一条 `message assistant`），用浏览器打开看看效果。样式对不对，这时候一目了然，不用等 JavaScript 写完。

---

## 2.4 JavaScript：让界面动起来

现在来写交互逻辑。先掌握两个基础：

**DOM 操作**：浏览器把 HTML 解析成一棵树，叫 DOM（Document Object Model）。JavaScript 通过 DOM API 来读写页面内容。最常用的是 `document.getElementById("某个id")`——拿到一个元素的引用，然后就可以改它的内容、样式、或者给它加子元素。

**事件监听**：用 `element.addEventListener("click", 函数)` 来监听事件。点击、输入、键盘按键，都是事件。事件触发时，浏览器调用你传入的函数。

现在来设计我们的 `main.js` 要做什么。

**`addMessage(text, role)` 函数**：创建一个消息气泡，追加到消息区域，并把滚动条滚到底部。`role` 是 `"user"` 或 `"assistant"`，决定气泡的样式。

**`showThinking()` / `hideThinking()`**：添加和移除"正在思考"的动画元素。它有一个固定的 id `"thinking-indicator"`，方便找到它删掉。

**`sendMessage()` 函数**：这是核心。流程是：拿到输入框的值 → 清空输入框 → 显示用户消息 → 显示思考动画 → 禁用发送按钮 → 发请求（现在先用 setTimeout 模拟）→ 收到响应后隐藏动画、显示回复 → 恢复按钮。

> **你可能会问**：为什么要把按钮禁用？用户点一下等一下不行吗？
>
> 如果不禁用，用户手快的话会点多次，发出多个请求。服务器收到多个请求，会返回多个回复，界面上就会出现重复的消息。禁用按钮是防止这种情况的标准做法。

### async/await 和 try/catch

发请求是一个异步操作——你发出去，要等服务器响应，这段时间不知道多长。JavaScript 用 `async/await` 来写异步代码，让它看起来像同步的：

```javascript
async function sendMessage() {
    const response = await fetch(...);  // 等这行完成，才继续往下
    const data = await response.json(); // 再等这行完成
    addMessage(data.reply, "assistant");
}
```

`await` 的意思是"等这个操作完成，把结果给我"。但只有在 `async` 函数里才能用 `await`。

网络请求随时可能出错，所以要用 `try/catch/finally`：
- `try` 里放可能出错的代码
- `catch` 在出错时执行——我们在这里显示一条红色的错误消息
- `finally` 不管成功还是失败都执行——在这里恢复发送按钮

这三件套在任何涉及网络请求的地方都会用到，是标准模板。

---

## 2.5 Enter 发送，Shift+Enter 换行

很多聊天应用都有这个行为：按 Enter 发送，按 Shift+Enter 换行。

实现方式：监听输入框的 `keydown` 事件，检查 `event.key === "Enter"` 且 `!event.shiftKey`，如果满足就触发发送，同时 `event.preventDefault()` 阻止 Enter 的默认行为（在 textarea 里默认是换行）。

还有一个小细节：`textarea` 的高度可以随输入内容自动增长。原理是每次 `input` 事件发生时，先把高度设为 `auto`（让它收缩到最小），然后再设为 `scrollHeight`（内容的实际高度）。这样输入越多，框越高，但有一个 `max-height` 限制，超过之后出现滚动条。

---

## 2.6 现在的效果

写完这一章，用浏览器打开 `index.html`，你应该能：
- 看到一个整洁的聊天界面，顶部有标题栏，底部有输入区
- 输入消息按 Enter 或点发送，用户消息出现在右侧
- 紧接着出现三个跳动的圆点
- 一秒后圆点消失，出现一条模拟的 AI 回复

这就是一个完整的前端——视觉上和真实应用没什么区别。唯一的区别是 AI 回复是假的，下一章做好后端，第四章把它们联起来。

> **试一下**：打开 Chrome 开发者工具（F12），切到 Console 面板。操作界面，看看有没有报错。如果有红色的错误信息，根据提示排查。Console 是你最重要的调试工具。

---

## 本章小结

- HTML 定义结构（骨架），CSS 定义样式（外观），JavaScript 实现交互（行为）
- Flexbox 布局：父元素 `display: flex`，子元素用 `flex: 1` 占满剩余空间
- `document.getElementById` 获取元素，`addEventListener` 监听事件，`appendChild` 添加子元素
- `async/await` 写异步代码，`try/catch/finally` 处理错误和清理工作
- F12 开发者工具是前端调试的核心，Console 看报错，Network 看请求

---

→ 下一章：[第 3 章：后端基础 - FastAPI](03-后端基础-FastAPI.md)
