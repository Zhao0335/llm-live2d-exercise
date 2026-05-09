"""
Edge-TTS provider。

用 Microsoft Edge 的免费 TTS 服务（pip install edge-tts），
零成本、无需 API key、质量不错，适合开发期。

依赖：
    pip install edge-tts
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ..core.providers import TTSProvider, TTSResult


class EdgeTTS(TTSProvider):
    name = "edge-tts"

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        volume: str = "+0%",
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume

    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        try:
            import edge_tts  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "edge-tts not installed. Run `pip install edge-tts`."
            ) from e

        voice = kwargs.get("voice", self.voice)
        communicate = edge_tts.Communicate(
            text,
            voice,
            rate=kwargs.get("rate", self.rate),
            volume=kwargs.get("volume", self.volume),
        )

        chunks = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.extend(chunk["data"])
        return TTSResult(audio_bytes=bytes(chunks), mime="audio/mpeg")
