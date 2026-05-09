# 大模型驱动 Live2D：技术分析与架构决策文档

> 本文档先梳理现有主流方案的技术路线，再分析它们的不足，最后给出本框架的架构决策与理由。
> 目的不是"再造一个 VTuber"，而是给出一个**可复用、可二次开发**的最小内核：把 LLM 的输出转化成 Live2D 的动作、表情、口型，其它（ASR / TTS / 前端壳子）都是可拔插的外围。

---

## 1. 问题域定义

"用大模型驱动 Live2D"展开后，需要解决以下几个独立子问题：

1. **文本生成（LLM）**：根据用户输入产生回复文本。需要支持流式输出，因为长回复一次性吐出会让 TTS 开口延迟过高。
2. **情绪/动作语义**：从 LLM 文本中分离"要说的话"与"该做的表情/动作"。否则模型只会念稿，不会眨眼、不会笑。
3. **语音合成（TTS）**：把文本转成可播放的音频。需要按句切分，边合成边播，否则首字延迟（TTFB）以秒计。
4. **口型同步（Lip-sync）**：让 Live2D 嘴巴跟着音频动。这件事必须发生在前端，因为浏览器端读取 PCM 振幅最简单可靠。
5. **表情/动作渲染**：把语义信号映射到 Live2D 的 `Expression` 和 `Motion`，并处理冲突（说话时不能突然切换表情打断口型）。
6. **传输层**：后端流式产物（文本 token、音频 chunk、表情指令）如何送到前端。HTTP SSE 或 WebSocket 二选一。
7. **状态管理**：会话历史、人格设定（system prompt）、可中断（用户打断 AI 说话）。

只有把这七件事拆开看，才能判断现有框架做得好不好。

---

## 2. 现有方案分析

### 2.1 Open-LLM-VTuber

**项目定位**：功能最全的开源 AI VTuber，Python 后端 + React/Electron 前端。支持几乎所有主流 ASR/TTS/LLM provider，支持 MCP 工具调用、长期记忆、桌宠模式、Bilibili 直播间集成。

**技术亮点**：
- 模块化的 ASR/TTS/LLM 抽象层，配置文件切换
- 通过后端推送的"emotion mapping"控制 Live2D 表情
- 支持流式句子链（speak by sentence chain）：LLM 边生成、TTS 边合成、前端边播
- 支持语音中断（用户说话时打断 AI）

**不足**：
- **耦合过重**。它是一个"产品"而不是"框架"。要做一个简单的网页问答机器人，需要把整个 ASR + TTS + Live2D + 桌宠模式 + MCP 都拉起来，启动配置文件几百行。
- **前端授权问题**。从 v1.2.0 开始，前端从 MIT 切换到自定义的 "Open-LLM-VTuber License 1.0"（搜索结果中也确认过这点）。如果要商业化集成，必须重写前端。
- **二次开发门槛高**。要嵌入到已有的 Web 应用里（比如客服站）很别扭，因为它假设自己是入口，而不是一个能被嵌入的组件。
- **Cubism 2.1 模型不再支持**（v1.2.0 起），老资源直接报废。

### 2.2 Persona Engine

**项目定位**：C# / .NET 桌面应用，专注于 VTubing 直播场景。通过 OBS Spout 把渲染结果推到直播软件。

**技术亮点**：
- VBridger 标准的 phoneme 级口型同步（比纯振幅口型更精确）
- 通过 emoji 情绪标签（`[EMOTION:🤩]`）触发表情，思路清晰

**不足**：
- **Windows-only / .NET 栈**。跨平台和嵌入 Web 都基本无解。
- **直播向架构**。它不是给 Web 应用用的，而是给主播一个人用的。
- **不能做服务化**。一台机器一个会话。

### 2.3 Live2D-LLM-Chat（suzuran0y）

**项目定位**：教学/演示项目，FunASR + LLM + CosyVoice + Live2D，更接近 demo。

**不足**：
- 单文件糊在一起，复用性差
- 没有处理流式与可中断
- 一旦想换个 TTS 就得改主流程

### 2.4 LLM-Live2D-Desktop-Assistant

**项目定位**：Open-LLM-VTuber 的 Electron 桌面分支，加入了 Claude Computer Use、唤醒词、唱歌（RVC）等功能。

**不足**：和 Open-LLM-VTuber 同源，架构问题同样继承下来。功能加得越多，作为"框架"的可复用性越差。

### 2.5 TEN Framework + Live2D 示例

**项目定位**：TEN 是一个实时多模态 Agent 框架（处理 STT→LLM→TTS pipeline），博客里展示了如何把 Live2D 嫁接上去。

**技术亮点**：
- 用 Live2D 官方的 MotionSync 做口型，比纯振幅好（基于 motionsync3.json 文件，按音频特征驱动多个嘴部参数，而不是一个 `MouthOpenY`）
- 强调 SSR 安全：用 Next.js 动态导入避免服务端报错，这点很多教程没注意到

**不足**：
- 依赖 TEN Framework 的整个 pipeline，灵活性受限
- MotionSync 配置文件不是所有 Live2D 模型都自带，门槛高

### 2.6 pixi-live2d-display 生态

**项目定位**：纯前端 Live2D 渲染库，不是 LLM 框架，但所有 Web 方案最终都要落到它（或它的 fork）上。

**关键事实**：
- 原版 `pixi-live2d-display`（guansss）**没有内置 lip-sync from audio**。这是个非常常见的踩坑点 —— 文档里有 `motion()` 但没有 `speak()`。
- `pixi-live2d-display-lipsyncpatch`（RaSan147 fork）补上了 `model.speak(audioUrl, options)` 接口，能播 mp3/wav 并自动驱动嘴部参数。这是目前事实标准。
- 都基于 PixiJS v7（注意不是 v8，v8 渲染管线变了）。
- 必须从 `<script>` 标签先加载 Cubism Core（`live2dcubismcore.min.js`），再加载老的 `live2d.min.js`（如果要支持 Cubism 2.1），最后才是 `pixi-live2d-display`。这个加载顺序文档里很容易忽略。

---

## 3. 共性问题总结

把上面这些方案放在一起看，能归纳出几个反复出现的问题：

| 问题 | 表现 |
|------|------|
| **产品 ≠ 框架** | 大多数项目在做一个"开箱即用的 VTuber"，不是给开发者复用的库。功能越多，越不能被嵌入。 |
| **协议不开放** | LLM 输出 → Live2D 控制信号的协议各家都自己定，导致前端无法独立于后端开发。 |
| **流式处理被忽视** | 很多项目把 LLM 完整输出拿到再 TTS，首字延迟动辄 5–10 秒。 |
| **情绪与说话耦合** | 表情指令混在文本里，前端要同时做"分词显示"和"动作触发"，逻辑容易乱。 |
| **口型方案碎片化** | 振幅 lip-sync、phoneme lip-sync、Live2D 官方 MotionSync 三套并存，且各方案对模型有不同要求。 |
| **打断不优雅** | 大多数实现没处理 barge-in：用户中途说话时，TTS 已经合成的音频还在播，体验割裂。 |

---

## 4. 本框架的设计决策

基于以上分析，本项目（暂命名 `llm-live2d`）做出以下决策。每条决策都对应上面提到的某个问题。

### 4.1 定位：内核 + 适配器，不做产品

**决策**：项目分两层：
- **Core**（`llm_live2d/core/`）：协议定义、流式 pipeline、事件总线。**与具体 LLM/TTS/Live2D 模型无关**。
- **Providers**（`llm_live2d/providers/`）：OpenAI / Anthropic / Edge-TTS 等具体实现，全部实现 Core 定义的抽象接口。

新加一个 LLM provider = 实现 `LLMProvider` 接口的 4 个方法；新加一个 TTS = 实现 `TTSProvider` 的 2 个方法。**不需要改 Core 一行代码**。

ASR 不内置在 Core 中 —— 因为不是所有用例都需要语音输入（很多场景就是文本对话 + Live2D 表演）。它作为可选的"上游 provider"接入，跟 LLM/TTS 平级。

### 4.2 定义清晰的中间协议：`Action` 流

**决策**：后端到前端只传一种结构 —— `Action` 事件流（JSON）。每个 Action 是以下几种之一：

```json
{"type": "say",        "text": "你好",        "id": "u1"}    // 一段要显示+朗读的文本
{"type": "audio",      "url": "/tts/u1.wav",  "id": "u1"}    // 对应音频
{"type": "expression", "name": "happy",       "hold_ms": 3000}
{"type": "motion",     "group": "TapBody",    "index": 0}
{"type": "thinking",   "text": "..." }                       // 内心独白，不朗读
{"type": "end",        "turn_id": "t-42"}                    // 一轮对话结束
```

LLM 的原始文本里嵌入情绪标签 `[emotion:happy]`、`[motion:wave]`、`<think>...</think>`，由后端的 `ActionParser` 解析成上面的 Action 流后再发给前端。前端**完全不接触 LLM 原文**，只消费结构化事件。

这样做的好处：
- 前端是纯渲染器，可以独立测试（直接喂一个 Action 列表 JSON 就能看到完整表演）
- 任何 LLM 都行，只要 system prompt 里教会它输出这些标签
- 协议升级不影响 provider 实现

### 4.3 流式 sentence-chain：边生成边说

**决策**：LLM 流式输出 → `SentenceSplitter` 按句号/问号/感叹号/换行切分 → 每凑够一句立刻送 TTS → TTS 完成立刻通过 WebSocket 发 `audio` Action。

具体实现：参考了 Open-LLM-VTuber 的 `speak_by_sentence_chain` 思路（搜索结果中提到过这个机制），但用 `asyncio.Queue` 实现得更简洁，避免他们那种内部回调嵌套。

时序大致是：
```
t=0.0s   用户输入到达
t=0.3s   LLM 第一个 token
t=0.8s   LLM 第一句完成（"你好啊。"）
t=0.8s   首句送入 TTS 队列
t=1.4s   首句音频生成完毕，前端开始播放 + 嘴动起来
t=1.5s   LLM 还在继续生成第二句…
```

第二句的 TTS 与第一句的播放并行。

### 4.4 口型同步：用 lipsyncpatch 的 `speak()`，不引入 MotionSync

**决策**：前端用 `pixi-live2d-display-lipsyncpatch`，调 `model.speak(audioUrl)`。

**理由**：
- 它内部基于 Web Audio API 做振幅分析，驱动 `ParamMouthOpenY` 这一个参数。**不需要 motionsync3.json**，对任意 Cubism 2/3/4 模型都能用。
- MotionSync 效果更好，但要求模型自带 `motionsync3.json` 配置；很多免费模型没有。本框架的目标是"任何 Live2D 模型放进来就能用"，所以选普适方案。
- 给二次开发者预留了升级口子：`Live2DController` 把口型实现抽成 `LipSyncStrategy` 接口，要换 MotionSync 改一个类即可。

### 4.5 传输层：WebSocket，不用 SSE

**决策**：前后端走 WebSocket。

**理由**：
- 需要双向 —— 用户中断（barge-in）、前端报告"音频播完了"等事件需要从前端推到后端。SSE 单向。
- 二进制音频可以走同一连接（一个 channel 两种消息：JSON 控制 + binary audio），减少 CORS / 鉴权两套逻辑。
- 真要换 SSE，把 `WSTransport` 换成 `SSETransport` 即可，业务代码不变。

### 4.6 可打断（barge-in）

**决策**：每轮对话有一个 `turn_id`。前端检测到用户开始说话（或主动点中断按钮），发 `{"type": "interrupt", "turn_id": "..."}`，后端立即：
1. 取消正在跑的 LLM 流
2. 清空 TTS 队列里没合成的句子
3. 给前端发 `{"type": "stop", "turn_id": "..."}`，前端停掉当前播放的音频和嘴动

会话历史里记录"AI 实际说出口的截止位置"，下次上下文里 AI 的回复就到那个位置为止 —— 否则模型会以为自己说完了。这是 Open-LLM-VTuber 的踩坑教训。

### 4.7 可观测性 & 二次开发友好

- **事件日志**：每个 Action 进出都记日志，便于回放调试。前端有"导入 Action 序列"开发模式，不连后端也能调试动画。
- **provider 协议有契约测试**：`tests/contracts/` 下有针对每种 provider 接口的最小测试集，自己写 provider 跑一下就知道有没有写对。
- **配置即代码**：`configs/*.yaml` 描述选用哪些 provider 与参数。改配置不用改代码。

---

## 5. 与现有方案的对比

| 维度 | Open-LLM-VTuber | Persona Engine | TEN+Live2D | **本框架** |
|------|---|---|---|---|
| 定位 | 完整产品 | 直播工具 | Pipeline 示例 | 可嵌入的库 |
| 跨平台 | ✓ | Windows | ✓ | ✓ |
| 流式句子链 | ✓ | ✓ | ✓ | ✓ |
| 协议开放 | 私有 | 私有 | 跟随 TEN | **公开 Action 协议** |
| 内核与外围解耦 | ✗（重） | ✗ | 跟随 TEN | **✓** |
| 加新 LLM provider 成本 | 中（懂全局） | 高 | 高 | **低（实现一个接口）** |
| 前端嵌入第三方应用 | 难（License + 依赖） | 几乎不可能 | 中 | **简单（纯组件）** |
| 可打断 | ✓ | 部分 | ✓ | ✓ |
| Cubism 2.1 兼容 | ✗（v1.2 已删） | ? | ✓ | **✓** |

---

## 6. 不会做的事（Non-goals）

为了保持"内核"的纯净，以下功能**不放进 Core**，只在 examples 里给参考：

- 桌宠/透明窗口（属于 Electron 壳子的事）
- 直播平台对接（弹幕拉取、OBS 推流）
- 长期记忆/RAG（属于上层 agent 的事）
- 唱歌、声音克隆（属于 TTS provider 的特化）
- 工具调用 / MCP（可以由 LLM provider 自己处理后再吐 token，Core 不感知）

这些不是不重要，而是它们和"驱动 Live2D"这个核心问题正交，混在一起会让框架失去焦点。

---

## 7. 后续路线

- v0.1（本次实现）：Core + OpenAI/Anthropic provider + Edge-TTS provider + WebSocket Server + 最小前端
- v0.2：MotionSync 口型策略；语音输入 provider（Whisper）
- v0.3：phoneme-level 口型（VBridger 风格）；多模型并发会话
- v0.4：插件系统，让第三方扩展 Action 类型（自定义动作）

—— 文档结束 ——
