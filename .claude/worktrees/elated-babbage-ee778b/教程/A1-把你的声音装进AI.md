# 番外篇 A1：把你的声音装进 AI 里

> 用 GPT-SoVITS 或 Fish Speech 克隆自己的声音，让虚拟形象用你的嗓子说话

---

## A1.1 为什么要训练自己的声音

Edge-TTS 挺好用的，但有一个问题：每个人用的声音都一样——微软的"晓晓"。你的 AI 助手听起来和别人的一模一样，没有任何个性。

如果你想让角色用你自己的声音说话，或者用某个特定风格的声音，或者做商业产品（Edge-TTS 有使用限制），就需要自己的声音模型。

**好消息**：现在的开源工具，只需要**几分钟的录音样本**就能克隆出质量不错的声音。不再需要几十小时的数据集。

---

## A1.2 选哪个方案

两个主流工具：

**GPT-SoVITS**：中文效果最好的开源 TTS，有 WebUI 图形界面，操作不复杂。需要 GPU（6GB 显存以上），5~30 分钟录音样本，训练一次大概 30~60 分钟。

**Fish Speech**：更新的工具，只需要 10 秒参考音频就能克隆声音，不需要训练，CPU 也能跑（慢但能用）。缺点是长文本偶尔漂移音色，稳定性稍差。

**推荐**：
- 有 GPU 且追求质量 → GPT-SoVITS
- 快速体验或没有 GPU → Fish Speech

---

## A1.3 录音：这步比训练更重要

模型质量 80% 取决于录音质量，20% 才是训练参数。录音马虎，训练再好也没用。

**格式要求**：WAV 格式，44100Hz，单声道，16bit。如果是 MP3 或 M4A，用 FFmpeg 转换：

```bash
ffmpeg -i your_recording.m4a -ar 44100 -ac 1 -sample_fmt s16 output.wav
```

**录音环境**：
- 关掉风扇、空调、冰箱压缩机
- 远离窗户
- 最好在衣柜旁边录（衣物吸音效果好）
- 戴耳机回听，确认没有底噪和爆音

**录什么内容**：朗读文章效果比聊天语音好，因为语速均匀、停顿一致。找一篇新闻稿或小说旁白，朗读 5~30 分钟，每句话结尾停顿 0.5 秒。

**不要录**：聊天语音（停顿不均匀，有"嗯""啊"），有音乐背景的录音，情绪极端的录音。

---

## A1.4 GPT-SoVITS 安装

**硬件需求**：NVIDIA GPU 6GB 显存以上。没有 GPU 的话，可以租 AutoDL / 阿里云 PAI 的 GPU 机器，A10 一小时约 3 元，训练 10 分钟数据大概花 1 块钱。

**Windows 用户（推荐方式）**：去 [github.com/RVC-Boss/GPT-SoVITS/releases](https://github.com/RVC-Boss/GPT-SoVITS/releases) 下载一键安装包（`install.bat`），双击运行，它会自动下载所有依赖。

**Linux / 手动安装**：

```bash
git clone https://github.com/RVC-Boss/GPT-SoVITS.git
cd GPT-SoVITS
conda create -n GPTSoVITS python=3.9
conda activate GPTSoVITS
pip install -r requirements.txt
python tools/download_models.py  # 下载预训练基础模型（几GB）
```

启动 WebUI：

```bash
python webui.py
# 打开 http://127.0.0.1:9874
```

---

## A1.5 GPT-SoVITS 训练流程

打开 WebUI，按照这个顺序操作：

**Step 1：音频切割**

在"音频切割"标签里，上传你的录音文件，设置切割阈值（静默超过 500ms 就切一刀），点击开始。生成的短片段保存在 `output/` 文件夹里。

**Step 2：语音识别**

在"语音识别"标签里，选择上一步的输出文件夹，选择中文，点击开始。Whisper 会自动识别每段录音的内容，生成 `.list` 标注文件。

完成后，**手动检查并纠正错误**——这步很重要，标注里的错字会直接影响训练质量。

**Step 3：训练 SoVITS 模型**

- 实验名随便起，比如 `my_voice`
- 参考音频路径：上一步生成的 `.list` 文件
- Batch size：4（显存 6GB）或 8（显存 8GB 以上）
- 总训练步数：8 个 epoch（几分钟数据用这个）

点击开始，训练进度显示在命令行里，大概 20~40 分钟（GPU）。

**Step 4：训练 GPT 模型**

同样在训练标签里，GPT 部分，参数类似，点击开始。GPT 训练比 SoVITS 快，5~15 分钟。

**Step 5：测试效果**

切到"TTS 推理"标签：
- 选择训练好的 SoVITS 模型（`.pth` 文件）
- 选择训练好的 GPT 模型（`.ckpt` 文件）
- 参考音频：从你的录音里找 3~10 秒的清晰一段
- 参考音频文字：手动填入这段录音说的内容
- 目标文字：你想合成的话

点击合成，听听效果。

---

## A1.6 启动 API 服务

训练好之后，启动 API 服务，让项目后端来调用：

```bash
python api_v2.py -a 0.0.0.0 -p 9880
```

调用格式：

```bash
curl "http://localhost:9880/tts" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，我是AI助手",
    "text_lang": "zh",
    "ref_audio_path": "/path/to/reference.wav",
    "prompt_text": "参考音频里说的内容",
    "prompt_lang": "zh"
  }' --output test.wav
```

返回 WAV 格式的音频文件。

---

## A1.7 接入项目：替换 tts.py

在 `backend/tts.py` 里，加一个新的后端选项：

```python
TTS_BACKEND = os.getenv("TTS_BACKEND", "edge")

async def synthesize(text: str) -> str:
    if TTS_BACKEND == "gptsovits":
        return await _synthesize_gptsovits(text)
    return await _synthesize_edge(text)

async def _synthesize_gptsovits(text: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{GPTSOVITS_URL}/tts",
            json={
                "text": text,
                "text_lang": "zh",
                "ref_audio_path": GPTSOVITS_REF_AUDIO,
                "prompt_text": GPTSOVITS_REF_TEXT,
                "prompt_lang": "zh",
            },
        )
        response.raise_for_status()
        audio_id = str(uuid.uuid4()).replace("-", "")
        audio_path = AUDIO_DIR / f"{audio_id}.wav"
        audio_path.write_bytes(response.content)
        return f"/audio/{audio_id}.wav"
```

在 `.env` 里切换后端，其他代码不需要改任何东西：

```bash
# 用 Edge-TTS（默认）
TTS_BACKEND=edge

# 换成 GPT-SoVITS（填入你的参考音频路径）
TTS_BACKEND=gptsovits
GPTSOVITS_URL=http://localhost:9880
GPTSOVITS_REF_AUDIO=/绝对路径/reference.wav
GPTSOVITS_REF_TEXT=这段参考音频里说的内容
```

---

## A1.8 Fish Speech：更简单的选择

如果不想折腾训练，**Fish Speech** 只需要 10 秒参考音频就能克隆声音，零训练，直接推理：

```bash
pip install fish-speech
# 或者用官方 Docker
docker run -it --gpus all fishaudio/fish-speech:latest
```

启动服务：

```bash
fish-speech serve --host 0.0.0.0 --port 8080
```

接入项目的方式和 GPT-SoVITS 类似——在 `tts.py` 里加一个 `_synthesize_fish_speech` 函数，通过 `.env` 变量切换。

Fish Speech 的优点是门槛极低，缺点是长文本音色稳定性不如 GPT-SoVITS——说长句子时音色可能会漂移。

---

## 本篇小结

- 录音质量 > 训练参数，安静环境 + 均匀语速 + 正确格式
- GPT-SoVITS：中文效果最好，需要 GPU，有 WebUI，5 步完成训练
- Fish Speech：10 秒即可克隆，无需训练，CPU 也能跑
- `TTS_BACKEND` 环境变量控制用哪个后端，项目代码完全不用改
- 本地运行：延迟更低，没有 API 费用，数据不出本机

---

→ 回到大纲：[00-大纲.md](00-大纲.md)
