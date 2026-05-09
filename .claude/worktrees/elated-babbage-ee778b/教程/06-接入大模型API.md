# 第 6 章：接入大模型 API

> 第 4 章的回复是几个 `if` 语句写死的假数据，这章把那个函数换成真正的 LLM API——只改这一个函数，其他的全部不动。

---

## 6.1 大模型 API 是怎么工作的

你向大模型发一个请求，它返回回复。这听起来很简单，但有一个关键细节：

**大模型本身是无状态的。** 它不知道你们之前聊过什么。每次请求对它来说都是第一次见面。

那 ChatGPT 怎么"记得"上下文？答案很直白：每次发请求，都把完整的对话历史一起发过去。

```
第 1 轮请求发的 messages：
  [你好]

第 2 轮请求发的 messages：
  [你好, AI回了什么, 然后呢]

第 3 轮请求发的 messages：
  [你好, AI回了什么, 然后呢, AI又回了什么, 接着说]
```

每轮都比上一轮多一点内容，模型读完整段历史，就知道"上下文"了。这也是为什么长对话越来越贵——发出去的文字越来越多，收费也按文字量算。

---

## 6.2 messages 格式：三种角色

发给大模型的消息是一个列表，每条消息有 `role` 和 `content` 两个字段：

- `system`：系统提示词，定义 AI 的角色和行为规则，用户看不到它，但 AI 会遵守
- `user`：用户说的话
- `assistant`：AI 的回复

一次完整的请求大概是这样：

```json
{
    "model": "deepseek-chat",
    "messages": [
        {"role": "system", "content": "你是一个友好的AI助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮你的？"},
        {"role": "user", "content": "今天天气怎么样"}
    ]
}
```

系统提示词放在最前面，然后是交替的 user 和 assistant 消息，最后是用户当前这条消息。

> **你可能会问**：系统提示词和用 `user` 角色说"你要扮演XXX"有什么区别？
>
> 理论上都能影响 AI 的行为，但 `system` 角色在大多数模型里权重更高，更难被用户输入"越狱"。而且语义上也更清晰——这是系统配置，不是对话内容。

---

## 6.3 选一个大模型服务

市面上的大模型服务，大多数都兼容 OpenAI 的接口格式——只有 `base_url` 和 `model` 名字不同，调用方式完全一样。

推荐初学者用 **DeepSeek**：价格便宜（几乎是 ChatGPT 的零头），中文效果好，国内访问速度快。去 [platform.deepseek.com](https://platform.deepseek.com) 注册，在 API Keys 页面生成一个 Key。

如果完全不想花钱，可以在本地用 **Ollama** 跑开源模型：下载安装 Ollama，`ollama pull qwen2.5:7b` 把模型拉下来，`ollama serve` 启动服务，接口地址是 `http://localhost:11434/v1`，格式和 OpenAI 完全兼容。缺点是需要还不错的显卡。

---

## 6.4 API Key 的安全管理

API Key 就像密码——泄露了别人可以以你的名义调用 API，费用算你头上。

**永远不要把 Key 写在代码里。** 代码可能会被上传到 GitHub，Key 就暴露了。

正确的做法是用 `.env` 文件存配置，然后把 `.env` 加到 `.gitignore` 里。在 `backend/` 目录下创建 `.env`：

```
LLM_API_KEY=sk-你的真实密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
SYSTEM_PROMPT=你是一个友好的AI助手，用中文回答问题。
```

然后在 Python 代码里用 `python-dotenv` 读取：

```bash
pip install python-dotenv httpx
```

在 `main.py` 最顶部：

```python
from dotenv import load_dotenv
load_dotenv()  # 读取 .env 文件，把里面的键值对变成环境变量
```

之后就可以用 `os.getenv("LLM_API_KEY")` 取到 Key 了。

---

## 6.5 写 llm.py：把 generate_reply 换成真的

新建 `backend/llm.py`。这个文件对外只暴露一个函数：`chat_once(history)` —— 接受对话历史列表，返回 AI 的回复字符串。

内部逻辑：
1. 从环境变量读取配置（base_url、key、model、system_prompt）
2. 构建 messages 列表（system 提示词 + 传入的历史）
3. 用 `httpx.AsyncClient` 发 POST 请求
4. 从响应里提取 `choices[0].message.content` 返回

关键代码结构：

```python
async with httpx.AsyncClient(timeout=60.0) as client:
    response = await client.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": 0.7,
            "stream": False,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
```

`timeout=60.0` 是说等最多 60 秒，超时了抛异常。大模型生成慢，60 秒一般够，但你可以根据需要调整。

`response.raise_for_status()` 是 httpx 的方法，如果响应状态码不是 2xx，自动抛出异常，省去手动检查。

---

## 6.6 更新 main.py

在 `main.py` 里，把原来的 `generate_reply` 函数删掉，改为从 `llm.py` 导入：

```python
from llm import chat_once
```

然后在 `/api/chat` 路由里：

```python
# 之前：
reply = generate_reply(request.message, history)

# 现在：
reply = await chat_once(history)
```

就这一行改动。其他的——session 管理、历史追加、响应格式——全部不动。这就是第 4 章把 `generate_reply` 单独写成函数的原因。

---

## 6.7 控制历史长度

对话越来越长，发给模型的文字越来越多，费用越来越高，还可能超出模型的上下文限制（模型一次能处理的最大文字量）。

解决方法：只保留最近 N 轮。在 `llm.py` 里：

```python
MAX_TURNS = 20  # 最多保留 20 轮

async def chat_once(history: list) -> str:
    # 取最近的记录，注意要保持 user/assistant 配对，所以 *2
    recent = history[-(MAX_TURNS * 2):]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + recent
    ...
```

这个数字可以根据你的预算和使用场景调整。

---

## 6.8 测试

重启后端，打开前端，输入一个问题——你应该能看到 AI 真正在"思考"，然后给出像样的回复。

> **试一下**：发几条消息，问 AI "你还记得我们聊过什么吗"，看它能不能把之前的对话内容说出来。如果能，说明历史传递是正确的。再问一个复杂问题，感受一下回复质量。
>
> 如果看到错误，去查后端日志。最常见的问题是 API Key 没配置好，或者 `.env` 文件路径不对。

---

## 6.9 现在的问题：用户要等很久

接入真实 LLM 之后，你会发现一个新问题：AI 在"思考"时，界面上那三个点要转很久——可能 3 秒、5 秒，甚至更长。全部生成完才显示，等待感很强。

这是因为我们现在用的是"非流式"模式——后端等 LLM 把所有字都生成完，才一次性返回给前端。

ChatGPT 的那种"边打字边显示"的效果，叫**流式输出（Streaming）**。下一章我们用 WebSocket 实现这个，让字一个一个出来，用户完全不需要等。

---

## 本章小结

- LLM 本身无状态，"记忆"靠每次把完整历史一起发过去实现
- `messages` 列表里有三种角色：`system`（系统提示）、`user`（用户）、`assistant`（AI）
- API Key 放在 `.env` 文件里，`.env` 加入 `.gitignore`，绝不写进代码
- `llm.py` 只暴露一个函数，`main.py` 只改一行调用——这就是模块化的价值
- 限制历史长度避免 Token 越来越多、越来越贵

---

→ 下一章：[第 7 章：流式输出 - WebSocket](07-流式输出-WebSocket.md)
