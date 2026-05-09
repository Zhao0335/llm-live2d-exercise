# 第 7 章：流式输出 —— WebSocket 与打字机效果

> 上一章接入了真实 LLM，但用户要盯着转圈圈等好几秒才能看到回复。这章用 WebSocket 改成流式输出——字一个一个冒出来，体验直接拉到 ChatGPT 的水平。

---

## 7.1 HTTP 为什么做不到打字机效果

先说清楚问题。

HTTP 的工作模式是：客户端发请求，服务器处理，返回完整响应，连接关闭。服务器**不能**主动给客户端推数据——只有客户端先开口，服务器才能说话。

LLM 生成文字是一个字一个字生成的过程，生成完一个字就知道了，没有必要等全部生成完再发。但 HTTP 只支持"全部准备好了再返回"，做不到"生成一个发一个"。

**WebSocket 的不同之处**：握手建立连接之后，双方都可以随时给对方发消息，连接持续存在，不会在每次通信后关闭。这就像打电话——线接通之后，任何时候任何一方都可以说话，而不是发短信（发一条等一条回复）。

有了 WebSocket，后端可以把 LLM 生成的每个字实时推给前端，前端收到就显示，用户看到的就是字在逐渐出现。

---

## 7.2 LLM 的流式 API

大模型 API 支持 `"stream": true` 参数。开启之后，响应不再是一个完整的 JSON，而是一行一行的数据流，每行包含一小块文字（叫做 Token）：

```
data: {"choices":[{"delta":{"content":"你"},"finish_reason":null}]}
data: {"choices":[{"delta":{"content":"好"},"finish_reason":null}]}
data: {"choices":[{"delta":{"content":"！"},"finish_reason":null}]}
data: {"choices":[{"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

每行的格式叫 SSE（Server-Sent Events）。我们需要：
1. 用 `httpx` 的流式模式逐行读取这些数据
2. 解析每行的 JSON，提取 `delta.content` 里的文字
3. 把文字通过 WebSocket 实时发给前端
4. 看到 `[DONE]` 就结束

---

## 7.3 后端：改造 llm.py 支持流式

在 `llm.py` 里新增一个 `chat_stream` 函数。这个函数是一个**异步生成器**——每生成一个 Token 就 `yield` 出去，调用方可以用 `async for` 逐个接收。

```python
async def chat_stream(history: list) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", ..., json={"stream": True}) as response:
            async for line in response.aiter_lines():
                # 解析每行，提取 token，yield 出去
                ...
                yield token
```

`yield` 和 `return` 的区别：`return` 一次性返回值然后函数结束，`yield` 返回一个值但函数"暂停"在这里，等调用方要下一个值时再继续。这就是生成器的工作原理——按需产出数据，不需要等全部生成完。

`async for line in response.aiter_lines()` 是 httpx 的异步逐行读取——每来一行数据就处理一行，不等整个响应结束。

原来的 `chat_once` 函数不用删，可以改成调用 `chat_stream` 来实现——把所有 Token 收集起来拼成字符串：

```python
async def chat_once(history: list) -> str:
    tokens = []
    async for token in chat_stream(history):
        tokens.append(token)
    return "".join(tokens)
```

---

## 7.4 后端：在 main.py 里加 WebSocket 路由

FastAPI 对 WebSocket 的支持非常简洁：

```python
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()  # 接受连接
    try:
        while True:
            raw = await websocket.receive_text()  # 等客户端发消息
            data = json.loads(raw)
            # 处理消息，流式生成，把 token 发回去
            async for token in chat_stream(history):
                await websocket.send_json({"type": "token", "text": token})
            await websocket.send_json({"type": "done", ...})
    except WebSocketDisconnect:
        pass  # 客户端断开，正常情况
```

`while True` 循环是因为一个 WebSocket 连接可以进行多轮对话——不是每次对话都重新建立连接，连接建好后一直用。

> **你可能会问**：为什么不用 HTTP + SSE，而要用 WebSocket？
>
> SSE 也能做流式输出，而且更简单。但 WebSocket 是双向的——客户端不只是等，还需要随时能发消息（比如打断生成、发新的对话）。如果只需要服务器单向推数据，SSE 也可以；这个项目用 WebSocket 因为后面的功能需要双向通信。

我们定义一个简单的消息协议，服务端发出的消息类型有三种：
- `{"type": "start", "session_id": "..."}`：开始生成，带上 session_id
- `{"type": "token", "text": "一个字"}`：每个 Token
- `{"type": "done", "history_length": N}`：生成结束
- `{"type": "error", "message": "..."}`：出错了

客户端发出的只有一种：
- `{"type": "message", "text": "用户输入", "session_id": "..."}`

---

## 7.5 前端：建立 WebSocket 连接

前端要做三件事：建立连接、发消息、接收 Token 并实时追加到界面。

**建立连接**：用 `new WebSocket(url)` 创建连接，注意 URL 前缀是 `ws://`（HTTP 是 `http://`，WebSocket 是 `ws://`；HTTPS 对应 `wss://`）。用第 5 章建立的 `WS_BASE` 变量：

```javascript
const ws = new WebSocket(`${WS_BASE}/ws/chat`);
```

连接有状态：`ws.onopen` 连接成功，`ws.onclose` 连接断开，`ws.onerror` 出错，`ws.onmessage` 收到消息。

**自动重连**：WebSocket 可能因为网络波动断开。在 `ws.onclose` 里加一个 `setTimeout`，5 秒后重新调用 `connect()` 函数，这样用户无感知地自动重连。

**处理消息**：在 `ws.onmessage` 里解析 JSON，根据 `type` 字段决定怎么处理：
- `"start"`：创建一个空的 AI 消息气泡，保存它的引用
- `"token"`：把文字追加到这个气泡，滚动到底部
- `"done"`：生成结束，恢复按钮状态
- `"error"`：显示错误消息

**流式追加文字**的关键：不是每次创建新气泡，而是先创建一个空气泡，然后不断往里面追加 `textContent`：

```javascript
// 收到 start 时
currentMessageEl = createAssistantBubble(); // 返回空气泡的内容元素

// 收到 token 时
currentMessageEl.textContent += data.text;
chatMessages.scrollTop = chatMessages.scrollHeight;
```

> **试一下**：把 WebSocket 的 URL 故意写错，看看浏览器 Console 里报什么错，以及界面上状态栏显示什么。这是模拟连接失败时的体验——确认错误提示足够清晰，用户知道发生了什么。

---

## 7.6 数据流动全貌

现在整个链路是：

```
用户输入 → ws.send() → 后端 WebSocket 路由
                              ↓
                        chat_stream(history)
                              ↓ 调 LLM API (stream=true)
                              ↓ 每来一个 token
                        ws.send_json({"type":"token", "text": ...})
                              ↓
前端 onmessage → currentMessageEl.textContent += token
                              ↓ LLM 生成完毕
                        ws.send_json({"type":"done", ...})
                              ↓
前端 → 恢复按钮，更新状态
```

从用户看到的角度：点发送 → 瞬间出现空气泡 → 字一个一个出现 → 生成完毕。整个过程没有"等待"的感觉，哪怕 LLM 要想 10 秒，前 0.3 秒就已经有字出来了。

---

## 7.7 效果验证

启动后端，打开前端，发一条消息。

你应该能看到：
- 状态栏变成"生成中..."
- 一个空气泡出现，然后文字开始一个字一个字地冒出来
- 生成完毕后状态恢复，可以继续发消息

> **试一下**：在生成过程中，打开 Chrome 开发者工具的 Network 面板，找到 `ws/chat` 那条连接，点进去看 Messages 标签。你能看到每一条发出和收到的 WebSocket 消息，包括每个 token 的内容。这是调试 WebSocket 问题最直接的方式。

---

## 本章小结

- WebSocket 是持久双向连接，服务器可以主动推数据
- LLM 的 `stream: true` 返回 SSE 格式的逐 Token 数据流
- `async for token in chat_stream()` 是异步生成器的用法——按需产出，不等全部完成
- 前端先创建空气泡，再用 `textContent +=` 逐字追加
- 用 `WS_BASE` 变量（第 5 章建立的）确保本地和服务器都能用

---

→ 下一章：[第 8 章：让 AI 能说也能听](08-让AI能说也能听.md)
