"""
llm_live2d.core.providers
=========================

各类 provider 的抽象接口。要新增 LLM/TTS 实现，继承对应的基类即可。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, List, Literal


# --------- Chat Message ---------

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


# --------- LLM Provider ---------


class LLMProvider(ABC):
    """
    LLM 抽象接口。

    实现要点：
    - 必须支持流式（异步生成器逐个 yield 文本片段）。
    - 必须能被外部 cancel —— 也就是说 `astream` 方法返回的生成器
      在被 `aclose()` 时要能优雅退出（asyncio 默认就是这个语义）。
    - provider 内部不要做任何句子切分或情绪解析，那是 ActionParser 的职责。
    """

    name: str = "abstract-llm"

    @abstractmethod
    async def astream(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式输出文本片段（chunk）。每次 yield 一个 token 或一小段文本。"""
        # NOTE: 这个 yield 让函数变成 async generator；子类覆盖即可。
        if False:
            yield ""  # pragma: no cover
        raise NotImplementedError


# --------- TTS Provider ---------


@dataclass
class TTSResult:
    """TTS 合成产物。"""
    audio_bytes: bytes  # 完整的音频文件字节（mp3/wav/ogg）
    mime: str           # 'audio/mpeg' / 'audio/wav' 等
    duration_ms: int = 0  # 已知时给，0 表示未知


class TTSProvider(ABC):
    """
    TTS 抽象接口。

    实现要点：
    - 输入是一句话（已经被 SentenceSplitter 切好），输出是一段完整音频。
    - 不要求流式 —— 句子粒度的延迟通常已经够用（< 1s）。
      如果某 provider 支持流式 PCM，可以在子类里另开方法，但本接口保持简单。
    """

    name: str = "abstract-tts"

    @abstractmethod
    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        ...


# --------- Audio Sink ---------


class AudioSink(ABC):
    """
    把 TTS 产物存到某个地方，并返回一个前端能取到的 URL。

    最常见实现：
    - InMemorySink: 存在内存字典里，URL 形如 /audio/<id>
    - S3Sink: 上传到对象存储，返回 CDN URL
    """

    @abstractmethod
    async def put(self, audio: TTSResult) -> str:
        """返回可访问 URL。"""
        ...

    @abstractmethod
    async def get(self, audio_id: str) -> TTSResult | None:
        ...
