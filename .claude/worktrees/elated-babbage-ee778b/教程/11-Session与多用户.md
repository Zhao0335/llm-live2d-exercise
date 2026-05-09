# 第 11 章：Session 与多用户

> 现在会话历史存在内存里，服务器一重启就全没了。这章把它存进数据库，顺便为多用户场景做好准备。

---

## 11.1 当前方案的问题

回顾一下我们现在的 Session 实现：

```python
sessions: dict[str, list] = {}  # 一个全局字典
```

简单，但有几个问题：

**重启就丢**：服务器重启、程序崩溃，字典消失，所有用户的历史全没了。

**内存无限增长**：用户越来越多，字典越来越大，迟早把内存撑满。

**不能跨设备**：用户换了浏览器或手机，原来的 session_id 还在，但字典里已经没有这个记录了。

**多进程不同步**：用 Nginx 负载均衡时，不同进程各有一个字典，同一个用户可能被路由到不同进程，读不到自己的历史。

解决方案：把 Session 存进数据库。数据库是持久的、所有进程共享的。

---

## 11.2 数据库选择

我们用 **SQLAlchemy** 的异步版本操作数据库，这样可以用一行配置在 SQLite 和 PostgreSQL 之间切换：

- **本地开发**：SQLite（零配置，就一个文件 `chat.db`）
- **生产服务器**：PostgreSQL（更稳健，支持并发）

SQLAlchemy 的**ORM（对象关系映射）**让我们用 Python 类和对象操作数据库，不用手写 SQL。你定义一个 Python 类说明"这是一张表，有哪些列"，SQLAlchemy 帮你生成 SQL、执行查询、把结果转成对象。

---

## 11.3 数据库设计

需要两张表：

**sessions 表**：记录每个会话，主键是 UUID 字符串，记录创建时间和最后活跃时间。

**messages 表**：记录每条消息，包含 session_id（外键）、role（user 或 assistant）、content（内容）、时间戳。

一个 session 对应多条 messages，这是标准的一对多关系。SQLAlchemy 用 `relationship` 来描述这个关系，之后查询时可以直接 `session.messages` 取出所有消息。

---

## 11.4 database.py

新建 `backend/database.py`，在这里定义数据模型和操作函数。

**创建引擎**：用 `create_async_engine`，传入数据库 URL。本地是 `sqlite+aiosqlite:///./chat.db`，生产环境换成 `postgresql+asyncpg://用户名:密码@localhost/数据库名`。

**模型定义**：继承 `DeclarativeBase` 的 `Base` 类，然后定义 `Session` 和 `Message` 两个模型类，用 `Column` 定义每列的名字和类型。

**初始化函数**：`init_db()` 调用 `Base.metadata.create_all`，自动建表——如果表已经存在就跳过，不会清空数据。这个函数在后端启动时调用一次。

**操作函数**，对外提供这几个：

`get_or_create_session(session_id)` ：如果传了 session_id 就查数据库，找到了返回它的历史，找不到就新建；如果没传 session_id 就直接新建。返回 `(session_id, history_list)`。

`append_messages(session_id, messages)` ：把新消息写进 messages 表，同时更新 session 的 `updated_at`。

`delete_session(session_id)` ：删除 session 及其所有消息（SQLAlchemy 的 `cascade="all, delete-orphan"` 会自动级联删除）。

---

## 11.5 更新 main.py

主要改动是把内存字典操作换成数据库操作。

**启动时初始化数据库**：FastAPI 的 `lifespan` 是处理启动/关闭逻辑的标准方式：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()   # 启动时建表
    yield             # 在这里提供服务
    # 关闭时可以加清理逻辑

app = FastAPI(lifespan=lifespan)
```

**WebSocket 路由里**，把：

```python
# 之前
session_id = data.get("session_id")
if not session_id or session_id not in sessions:
    session_id = str(uuid.uuid4())
    sessions[session_id] = []
history = sessions[session_id]
```

换成：

```python
# 现在
session_id, history = await get_or_create_session(data.get("session_id"))
```

生成完毕后，把对话存到数据库：

```python
await append_messages(session_id, [
    {"role": "user", "content": user_text},
    {"role": "assistant", "content": clean_reply},
])
```

这两处改动，其他逻辑完全不变。

---

## 11.6 安装新依赖

```bash
pip install sqlalchemy aiosqlite
```

如果之后要用 PostgreSQL，还需要：

```bash
pip install asyncpg
```

---

## 11.7 测试持久化

> **试一下**：
> 1. 启动后端，发几条消息，注意记下顶部显示的 session_id（或者从 Console 里复制）
> 2. Ctrl+C 停止后端
> 3. 重新启动
> 4. 打开前端，在 session_id 字段里填入刚才记下的 ID，发一条消息
> 5. AI 应该记得之前说过的话——对话历史持久化成功

---

## 11.8 定期清理过期会话

会话会越来越多，需要定期清理很久没活跃的。可以在 `lifespan` 里加一个后台任务，每隔 24 小时删一次 7 天没活跃的会话：

```python
async def scheduled_cleanup():
    while True:
        await asyncio.sleep(24 * 3600)
        # 删除 7 天前的会话
        ...

asyncio.create_task(scheduled_cleanup())
```

`asyncio.create_task()` 创建一个后台协程，不阻塞主程序。它会在后台每 24 小时运行一次，主程序该干嘛干嘛。

---

## 11.9 切换到 PostgreSQL（生产环境）

在服务器上安装 PostgreSQL 并创建数据库之后，只需要改 `.env` 里的一行：

```
DATABASE_URL=postgresql+asyncpg://用户名:密码@localhost/数据库名
```

代码不需要改任何一行。这就是 ORM 的价值——数据库换了，应用代码不变。

---

## 本章小结

- 内存字典 → 数据库：持久、跨进程共享、不怕重启
- SQLAlchemy 异步 ORM：Python 类描述表结构，操作函数封装 CRUD
- `lifespan` 是 FastAPI 处理启动/关闭逻辑的标准方式
- SQLite（开发）→ PostgreSQL（生产），改一行配置，代码不变
- 定期清理旧会话：`asyncio.create_task()` 启动后台任务

---

→ 下一章：[第 12 章：数据库与用户认证](12-数据库与用户认证.md)
