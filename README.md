# llm-live2d

> 一个**可二次开发**的最小框架：用 LLM 驱动 Live2D 模型说话、做表情、做动作。
> 核心层不依赖任何具体 LLM/TTS/前端框架；外围 provider 可热插拔。

完整设计动机和与现有方案的对比，见 [`docs/TECHNICAL_ANALYSIS.md`](docs/TECHNICAL_ANALYSIS.md)。

## 项目结构

```
llm-live2d/
├── docs/
│   └── TECHNICAL_ANALYSIS.md      # 技术分析与设计决策
│
├── backend/
│   ├── llm_live2d/
│   │   ├── core/                  # 内核：协议 + Pipeline + 抽象接口
│   │   │   ├── actions.py         #   Action 协议（前后端唯一约定）
│   │   │   ├── providers.py       #   LLMProvider / TTSProvider / AudioSink 抽象
│   │   │   ├── splitter.py        #   流式文本 → 整句切分
│   │   │   ├── parser.py          #   解析 LLM 输出里的 [emotion:] / <think>
│   │   │   └── pipeline.py        #   编排 LLM + Parser + Splitter + TTS
│   │   ├── providers/             # 具体实现（按需依赖）
│   │   │   ├── openai_llm.py      #   任意 OpenAI 兼容服务
│   │   │   ├── edge_tts_provider.py  # Microsoft Edge 免费 TTS
│   │   │   └── memory_sink.py     #   内存 audio sink
│   │   └── server/
│   │       └── ws_server.py       # FastAPI WebSocket 服务
│   ├── pyproject.toml
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── Live2DController.js    # 封装 pixi-live2d-display(-lipsyncpatch)
│   │   └── ActionClient.js        # WebSocket + Action 串行消费
│   └── public/
│       ├── index.html             # 静态入口
│       ├── style.css
│       └── main.js
│
├── examples/
│   └── run_server.py              # 最小可运行例子
│
└── configs/
    └── default.yaml               # 配置即代码（预留）
```

## 快速开始

### 1) 启后端

```bash
cd backend
pip install -e .
pip install edge-tts uvicorn[standard]

cd ..
export OPENAI_API_KEY=sk-...
# 也可以指向兼容服务：
# export OPENAI_BASE_URL=https://api.deepseek.com/v1
# export OPENAI_MODEL=deepseek-chat

python examples/run_server.py
```

### 2) 启前端

```bash
# 任意静态服务器都可以
cd frontend/public
python -m http.server 5173
# 浏览器打开 http://localhost:5173
```

也可以通过 query 参数指定其它 Live2D 模型和 ws 地址：

```
http://localhost:5173/?model=/models/yourchar/yourchar.model3.json&ws=ws://localhost:8000/ws
```

## 核心概念

### Action 协议

后端不直接把 LLM 的原文吐给前端。LLM 输出形如：

```
[emotion:happy]你好呀！[motion:Wave]很高兴见到你。<think>对方看起来很开心</think>
```

经过后端 `ActionParser` + `SentenceSplitter` + TTS 处理后，**前端收到的是结构化 Action 流**：

```jsonl
{"type": "turn_start", "turn_id": "t-3a91"}
{"type": "expression", "name": "happy", "hold_ms": 3000}
{"type": "say",       "text": "你好呀！", "id": "u-aa01"}
{"type": "audio",     "url": "/audio/xxxxxx.mp3", "say_id": "u-aa01"}
{"type": "motion",    "group": "Wave"}
{"type": "say",       "text": "很高兴见到你。", "id": "u-aa02"}
{"type": "audio",     "url": "/audio/yyyyyy.mp3", "say_id": "u-aa02"}
{"type": "thinking",  "text": "对方看起来很开心"}
{"type": "turn_end",  "turn_id": "t-3a91"}
```

前端只需消费这些事件，不关心 LLM 是 OpenAI 还是 DeepSeek，TTS 是 Edge 还是 GPTSoVITS。

### 流式句子链

LLM 是流式输出，每凑够一句立刻送 TTS。第一句的 TTS 大约 0.5–1.5s 完成 → 用户能在 1 秒级看到 AI 开口。第二句的 TTS 与第一句的播放并行，整体响应延迟显著低于"全文生成完再 TTS"的方案。

### 可打断（barge-in）

前端点中断按钮 / WebSocket 发 `{"type": "interrupt"}` 后：

1. 后端立即取消 LLM 流和 pending TTS 任务
2. 前端立即停止当前播放音频，嘴巴回到闭合
3. 会话历史只记录"实际说出口"的部分，下一轮上下文不会以为 AI 把整段话说完了

## 二次开发

### 加一个新的 LLM provider

实现 `LLMProvider`：

```python
from llm_live2d.core import LLMProvider, ChatMessage

class MyLLM(LLMProvider):
    name = "my-llm"

    async def astream(self, messages: list[ChatMessage], **kwargs):
        # 调用你的服务，逐 token yield 字符串即可
        async for token in my_service.stream(...):
            yield token
```

塞给 `Pipeline` 就完事了。

### 加一个新的 TTS provider

实现 `TTSProvider`：

```python
from llm_live2d.core import TTSProvider, TTSResult

class MyTTS(TTSProvider):
    name = "my-tts"

    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        audio_bytes = await my_tts_service.synth(text)
        return TTSResult(audio_bytes=audio_bytes, mime="audio/mpeg")
```

### 把前端嵌入已有 Web 应用

`Live2DController` 和 `ActionClient` 是纯 JS class，零依赖框架（不依赖 React/Vue），可以直接 import 进 React/Vue/Svelte 组件，把 canvas ref 和后端 ws 地址传进去就能用。

### 换传输层（HTTP SSE / Socket.IO / gRPC）

`Pipeline.handle_user_message()` 返回的是 `AsyncIterator[Action]`，与传输层无关。`backend/llm_live2d/server/ws_server.py` 只是其中一个适配器；照葫芦画瓢就能写 SSE 版。

## 注意事项 / 常见坑

- **PixiJS 必须用 v7**。v8 渲染管线变了，`pixi-live2d-display` 还没适配。
- **`pixi-live2d-display` 原版没有 `model.speak()`**。本项目 index.html 里默认引入的是 `pixi-live2d-display-lipsyncpatch` fork。
- **Cubism Core 必须在 `pixi-live2d-display` 之前加载**。index.html 里的 `<script>` 顺序不要随便调。
- **Live2D 模型版权**：项目自身是 MIT，但 Live2D 官方 sample 模型受 Live2D Inc. 自己的 license 约束，商用前请单独确认。
- **跨域**：浏览器从 `http://localhost:5173` 连 `ws://localhost:8000/ws` 没事，但去 fetch `http://localhost:8000/audio/xxx.mp3` 时需要 server 设置 CORS。本项目已在 `create_app(cors_origins=...)` 里处理。

## 路线

- v0.1（现在）：核心 + OpenAI/Anthropic 兼容 LLM + Edge-TTS + WS server + 最小前端
- v0.2：YAML 配置加载器；Whisper 语音输入 provider；MotionSync 口型策略
- v0.3：phoneme 级口型（VBridger 风格）；多会话隔离
- v0.4：Action 类型插件机制
