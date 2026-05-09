"""
最小可运行示例：启动一个 WebSocket 服务，
用 OpenAI 兼容 API + Edge-TTS 驱动 Live2D 前端。

运行：
    export OPENAI_API_KEY=sk-...
    # 可选：换其他兼容服务
    # export OPENAI_BASE_URL=https://api.deepseek.com/v1
    # export OPENAI_MODEL=deepseek-chat
    python -m examples.run_server

然后用浏览器打开 frontend/public/index.html（或起个静态服务器指向 frontend/public）。
"""
from __future__ import annotations

import logging
import os

import uvicorn

from llm_live2d.core import Pipeline, PipelineConfig
from llm_live2d.providers import EdgeTTS, InMemoryAudioSink, OpenAICompatLLM
from llm_live2d.server import create_app


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Please set OPENAI_API_KEY (or compatible service key).")

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    voice = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")

    sink = InMemoryAudioSink(url_prefix="/audio")

    def make_pipeline() -> Pipeline:
        # 每个 WS 连接独立一份 LLM 客户端 + 独立历史。
        llm = OpenAICompatLLM(api_key=api_key, base_url=base_url, model=model)
        tts = EdgeTTS(voice=voice)
        config = PipelineConfig(
            system_prompt=(
                "你是虚拟形象小语。严格规则：\n"
                "1. 每句话前必须加 [emotion:xxx]，xxx 只能是 f01/f02/f03/f04\n"
                "2. f01=平静，f02=难过，f03=生气，f04=开心\n"
                "3. 格式：[emotion:f04]你好！[emotion:f01]今天怎么样？\n"
                "4. 禁止括号描述动作\n"
            ),
        )
        return Pipeline(llm=llm, tts=tts, sink=sink, config=config)

    app = create_app(
        make_pipeline,
        sink=sink,
        cors_origins=["*"],
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
