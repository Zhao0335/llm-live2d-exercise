# 第 3 章：后端基础 —— FastAPI

> 上一章我们把前端做好了，但按发送之后只有一秒钟的假回复。这章来写后端——一个真正能接收消息、处理请求、返回数据的 Python 服务。

---

## 3.1 先说 Python 里最重要的概念：字典和列表

我们的后端会大量用到这两个数据结构。

**字典（dict）**：键值对的集合，就是 JSON 在 Python 里的样子。

```python
message = {
    "role": "user",
    "content": "你好"
}
print(message["role"])   # 输出：user
```

**列表（list）**：有顺序的集合。聊天历史就是一个列表，每条消息是一个字典。

```python
history = []
history.append({"role": "user", "content": "你好"})
history.append({"role": "assistant", "content": "你好！"})
print(len(history))  # 2
```

这两个结构，你在这个项目里会写几百次。先把感觉找到。

---

## 3.2 异步编程：为什么 FastAPI 用 async/await

这是理解后端的关键一步，花两分钟想清楚。

你的服务器同时收到 100 个用户的请求，每个请求都要等大模型 API 响应——可能要 3 秒。

**同步方式**：一个一个处理，第 1 个处理完再处理第 2 个。第 100 个用户要等 300 秒，早就断开了。

**异步方式**：发出第 1 个 API 请求之后，不傻等它返回，立刻去处理第 2 个请求。等第 1 个请求的结果回来了，再继续处理它。CPU 没有闲着，效率极高。

Python 用 `async def` 和 `await` 来实现异步：

- `async def` 定义一个"可以被暂停和恢复"的函数，叫**协程**
- `await` 的意思是"暂停在这里，等这个操作完成，然后继续"
- 暂停期间，Python 去做别的事——这就是异步的精髓

```python
async def call_llm(message):
    # await 在这里暂停，等 API 返回
    # 等待期间，其他请求可以继续进来
    response = await http_client.post(...)
    return response
```

FastAPI 是为异步设计的框架，路由函数用 `async def` 定义，就能同时处理大量请求。

> **你可能会问**：我把路由函数写成普通的 `def` 行不行？
>
> 可以，FastAPI 会把它放到线程池里运行，不会阻塞主线程。但如果你的函数里有 `await`（比如异步数据库查询），就必须用 `async def`。这个项目里我们全程用 `async def`，养成好习惯。

---

## 3.3 FastAPI 的核心：路由装饰器

FastAPI 定义接口的方式非常直观：写一个函数，在上面贴一个装饰器，说明"什么方法、什么路径触发这个函数"。

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/hello")
async def say_hello():
    return {"message": "你好"}
```

`@app.get("/hello")` 的意思就是：当有人发来 GET 请求访问 `/hello` 路径时，调用 `say_hello` 函数，把它的返回值作为响应。函数返回字典，FastAPI 自动转成 JSON。

**路径参数**：在路径里用花括号，比如 `/users/{user_id}`，FastAPI 会从 URL 里提取这个值，传给函数：

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}
# 访问 /users/42 → {"id": 42}
```

注意 `user_id: int`——FastAPI 会自动把 URL 里的字符串转成整数，如果转不了（比如 `/users/abc`），自动返回 422 错误。

---

## 3.4 POST 请求和请求体：Pydantic 的魔法

GET 请求适合查询，POST 请求适合提交数据。聊天接口是 POST，因为用户在发消息。

POST 请求的数据放在**请求体（Body）**里，格式是 JSON。FastAPI 用 **Pydantic** 的 `BaseModel` 来描述这个 JSON 的结构：

```python
from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    message: str                    # 必填，字符串
    session_id: Optional[str] = None  # 选填，不传时是 None
```

然后在路由函数里接收它：

```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    print(request.message)  # 直接用，已经是正确类型了
    return {"reply": "收到了"}
```

Pydantic 的好处是：你不需要手动检查"message 字段有没有传"、"类型对不对"——FastAPI 帮你做了，格式不对自动返回 422 错误，还附带说明。

> **你可能会问**：为什么要专门定义一个类，直接从请求里拿 JSON 不行吗？
>
> 当然可以拿，但那样你要自己验证每个字段，容易漏，也容易出错。Pydantic 相当于一个自动验证器：你声明"这个字段必须是字符串"，它就帮你保证。省心，而且错误信息清晰。

---

## 3.5 CORS：前端访问后端时的拦路虎

开发阶段你会遇到这个问题：前端和后端地址不一样——前端可能是从文件系统打开的 `file://...`，后端是 `http://localhost:8000`。浏览器看到这两个"来源"不同，默认拒绝请求，报一个 CORS 错误。

解决方法是在后端加 CORS 中间件，告诉浏览器"我允许跨域请求"：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 允许所有来源，开发时用
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**中间件**是请求在到达路由函数之前经过的处理层。CORS 中间件的作用是给每个响应加上必要的 HTTP 头，告诉浏览器"可以放行"。

第 4 章我们还会讲另一个解决 CORS 的方式——让后端直接提供前端文件，那样两者同源，CORS 问题根本不会出现。

---

## 3.6 让后端提供前端文件：StaticFiles

FastAPI 可以直接把一个文件夹里的静态文件（HTML/CSS/JS）暴露给浏览器访问：

```python
from fastapi.staticfiles import StaticFiles

# 把 frontend 文件夹挂载到根路径
# html=True 表示访问 / 时返回 index.html
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")
```

注意要把 `mount` 放在所有路由定义的**最后面**，否则 FastAPI 会把 API 路由也交给静态文件服务处理，导致 API 失效。

---

## 3.7 写一个完整的后端

现在把前面的东西拼起来，写 `backend/main.py`。

需要做的事：
1. 创建 FastAPI 实例，加 CORS 中间件
2. 定义请求体模型（message 字段）
3. 写 `/api/chat` 路由，接收消息，返回一个假回复
4. 写一个 `/api/health` 检查接口——这是好习惯，方便确认服务是否存活
5. 挂载静态文件（放最后）

启动方式：

```bash
cd backend
uvicorn main:app --reload
```

> **试一下**：启动后端，访问 `http://127.0.0.1:8000/docs`。找到 `/api/chat` 接口，点 "Try it out"，在请求体里填 `{"message": "你好"}`，点 Execute。看看返回了什么，状态码是不是 200。
>
> 这是不用写任何前端代码就能测试后端的方式。以后每写一个新接口，都先来这里验证。

---

## 3.8 前端对接后端

前端的 `sendMessage` 函数里，现在还是假数据。把 `setTimeout` 那段换成真正的 `fetch`：

```javascript
const response = await fetch("http://localhost:8000/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
});
const data = await response.json();
addMessage(data.reply, "assistant");
```

前端和后端现在能说话了——但是 HTTP 没有记忆，每次请求对后端来说都是第一次见面。下一章我们解决这个问题，加上会话（Session）。

---

## 3.9 理解错误处理

后端有时候需要主动告诉前端"你发来的数据有问题"或者"我这边出错了"。FastAPI 用 `HTTPException` 来做这件事：

```python
from fastapi import HTTPException

@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    ...
```

抛出这个异常，FastAPI 会把它转成对应状态码的 HTTP 响应，前端拿到 400 或 500 的状态码，就知道出问题了。前端的 `try/catch` 里可以根据状态码决定怎么提示用户。

---

## 本章小结

- 异步（`async def` + `await`）让服务器能同时处理大量等待 I/O 的请求
- FastAPI 用装饰器（`@app.get` / `@app.post`）定义路由，路由函数的返回值自动转成 JSON
- Pydantic 的 `BaseModel` 负责请求体的结构定义和自动验证
- CORS 中间件解决跨域问题，`StaticFiles` 让后端直接提供前端文件
- `HTTPException` 主动返回错误状态码

---

→ 下一章：[第 4 章：最小可行版本 - HTTP 聊天](04-最小可行版本-HTTP聊天.md)
