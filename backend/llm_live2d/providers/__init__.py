"""具体 provider 实现。每个 provider 都依赖第三方库（按需 import）。"""
from .edge_tts_provider import EdgeTTS
from .memory_sink import InMemoryAudioSink
from .openai_llm import OpenAICompatLLM

__all__ = ["OpenAICompatLLM", "EdgeTTS", "InMemoryAudioSink"]
