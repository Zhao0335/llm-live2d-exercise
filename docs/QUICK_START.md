# llm-live2d 快速上手指南

## 一、启动步骤（完整版）

### 1. 安装依赖（首次运行）

```powershell
# 激活 conda 环境
conda activate llm2d

# 进入项目目录
cd d:\llm-live2d\llm-live2d\backend

# 安装项目
pip install -e .

# 安装 edge-tts（可选，用于语音合成）
pip install edge-tts
```

### 2. 启动后端服务器

**方式 1：使用启动脚本（推荐）**

```powershell
cd d:\llm-live2d\llm-live2d
.\start-server.ps1
```

**方式 2：手动启动**

```powershell
cd d:\llm-live2d\llm-live2d
$env:OPENAI_API_KEY="你的API密钥"
python examples/run_server.py
```

看到以下输出表示成功：
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 3. 启动前端静态服务器

**新开一个终端窗口**：

```powershell
cd d:\llm-live2d\llm-live2d\frontend\public
python -m http.server 5173
```

看到以下输出表示成功：
```
Serving HTTP on :: port 5173 (http://[::]:5173/) ...
```

### 4. 打开浏览器

访问：http://localhost:5173

---

## 二、Live2D 模型配置

### 方式 1：使用默认模型（无需配置）

项目默认使用 CDN 上的免费模型，**不需要下载任何模型文件**。

直接访问 http://localhost:5173 即可看到角色。

### 方式 2：使用自己的模型

#### 步骤 1：准备模型文件

Live2D 模型通常包含以下文件：

```
yourchar/
├── yourchar.model3.json    ← 模型配置文件（必需）
├── yourchar.moc3           ← 模型数据（必需）
├── textures/               ← 贴图文件夹
│   ├── texture_00.png
│   └── ...
├── motions/                ← 动作文件夹（可选）
│   ├── idle_01.motion3.json
│   ├── tap_body.motion3.json
│   └── ...
└── expressions/            ← 表情文件夹（可选）
    ├── happy.exp3.json
    └── ...
```

#### 步骤 2：放置模型文件

把模型文件夹放到 `frontend/public/models/` 目录下：

```
frontend/public/
├── models/
│   └── yourchar/              ← 你的模型文件夹
│       ├── yourchar.model3.json
│       ├── yourchar.moc3
│       └── ...
```

#### 步骤 3：通过 URL 参数指定模型

访问时添加 `model` 参数：

```
http://localhost:5173/?model=/models/yourchar/yourchar.model3.json
```

#### 步骤 4：指定 WebSocket 地址（可选）

如果后端不在同一台机器，添加 `ws` 参数：

```
http://localhost:5173/?model=/models/yourchar/yourchar.model3.json&ws=ws://your-server-ip:8000/ws
```

---

## 三、模型表情和动作配置

### 1. 查看模型支持的表情和动作

打开 `yourchar.model3.json` 文件，找到 `Expressions` 和 `Motions` 部分：

```json
{
  "FileReferences": {
    "Expressions": [
      { "Name": "happy", "File": "expressions/happy.exp3.json" },
      { "Name": "sad", "File": "expressions/sad.exp3.json" }
    ],
    "Motions": {
      "Idle": [
        { "File": "motions/idle_01.motion3.json" }
      ],
      "TapBody": [
        { "File": "motions/tap_body.motion3.json" }
      ]
    }
  }
}
```

### 2. 在 LLM 提示词中配置

修改 `examples/run_server.py` 中的 `system_prompt`：

```python
config = PipelineConfig(
    system_prompt=(
        "你是一个友好的虚拟形象。回复时可以用以下控制标签："
        "[emotion:happy] / [emotion:sad] 切换表情；"  # 使用模型支持的表情名
        "[motion:Idle] / [motion:TapBody] 触发动作。"  # 使用模型支持的动作组名
        "保持轻松自然，不要刻意大量加标签。"
    ),
)
```

**重要**：`[emotion:XXX]` 和 `[motion:YYY]` 中的 XXX 和 YYY 必须是模型实际支持的表情名和动作组名。

---

## 四、使用其他 LLM 服务

### 1. 使用 DeepSeek

```powershell
$env:OPENAI_API_KEY="你的DeepSeek密钥"
$env:OPENAI_BASE_URL="https://api.deepseek.com/v1"
$env:OPENAI_MODEL="deepseek-chat"
python examples/run_server.py
```

### 2. 使用本地模型（如 Ollama）

```powershell
$env:OPENAI_API_KEY="ollama"  # 任意值
$env:OPENAI_BASE_URL="http://localhost:11434/v1"
$env:OPENAI_MODEL="llama3"
python examples/run_server.py
```

---

## 五、TTS 语音配置

### 1. 查看可用的声音

```powershell
edge-tts --list-voices | Select-String "zh-CN"
```

### 2. 修改声音

```powershell
$env:TTS_VOICE="zh-CN-YunxiNeural"  # 男声
# 或
$env:TTS_VOICE="zh-CN-XiaoyiNeural"  # 女声
python examples/run_server.py
```

常用中文声音：
- `zh-CN-XiaoxiaoNeural` - 晓晓（女声，默认）
- `zh-CN-YunxiNeural` - 云希（男声）
- `zh-CN-XiaoyiNeural` - 晓伊（女声，活泼）
- `zh-CN-YunjianNeural` - 云健（男声，成熟）

---

## 六、常见问题

### Q1: 页面打开后看不到 Live2D 角色

**原因**：模型加载失败

**解决**：
1. 打开浏览器开发者工具（F12）查看 Console 错误
2. 检查模型 URL 是否正确
3. 如果使用自己的模型，确保文件路径正确

### Q2: 发送消息后没有反应

**原因**：后端未启动或 API Key 未设置

**解决**：
1. 检查后端终端是否有错误输出
2. 确认环境变量已设置：`echo $env:OPENAI_API_KEY`
3. 检查 API Key 是否有效

### Q3: 角色说话但没有声音

**原因**：TTS 未安装或配置错误

**解决**：
1. 安装 edge-tts：`pip install edge-tts`
2. 检查后端日志是否有 TTS 错误

### Q4: 表情或动作不生效

**原因**：模型不支持该表情/动作，或名称不匹配

**解决**：
1. 打开模型的 `.model3.json` 文件
2. 查看支持的 `Expressions` 和 `Motions`
3. 修改 `system_prompt` 使用正确的名称

### Q5: CORS 错误

**原因**：前端和后端不在同一域名/端口

**解决**：
1. 确保使用 `http://localhost:5173` 访问前端
2. 检查后端 `cors_origins` 配置（默认允许所有来源）

---

## 七、项目文件结构说明

```
llm-live2d/
├── backend/                    ← 后端代码
│   ├── llm_live2d/
│   │   ├── core/              ← 核心逻辑（不要修改）
│   │   ├── providers/         ← LLM/TTS 实现（可扩展）
│   │   └── server/            ← WebSocket 服务器
│   └── tests/                 ← 测试代码
│
├── frontend/                   ← 前端代码
│   ├── src/                   ← 核心模块
│   │   ├── ActionClient.js    ← WebSocket 客户端
│   │   └── Live2DController.js ← Live2D 控制器
│   └── public/                ← 静态文件（部署这个目录）
│       ├── index.html         ← 入口页面
│       ├── main.js            ← 主逻辑
│       ├── style.css          ← 样式
│       └── models/            ← 放你的 Live2D 模型
│
├── examples/                   ← 示例代码
│   └── run_server.py          ← 启动服务器
│
└── configs/                    ← 配置文件（预留）
```

---

## 八、下一步

1. **阅读代码带读文档**：[docs/CODE_READING_GUIDE.md](docs/CODE_READING_GUIDE.md)
2. **尝试修改 system_prompt**：让角色有不同的性格
3. **添加自己的模型**：使用你喜欢的 Live2D 角色
4. **扩展功能**：添加新的 Action 类型或 Provider

有问题随时问！
