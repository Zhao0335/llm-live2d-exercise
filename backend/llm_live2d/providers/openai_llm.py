"""
OpenAI 兼容的 LLM provider。

所以这一份代码可以接入大量后端。只需改 base_url + model + api_key。
"""
from __future__ import annotations

from typing import AsyncIterator, List, Optional
import json

import httpx

from ..core.providers import ChatMessage, LLMProvider


class OpenAICompatLLM(LLMProvider):
    name = "openai-compat"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.7,
        timeout: float = 60.0,
        extra_headers: Optional[dict] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    async def astream(
        self,
        messages: List[ChatMessage],
        **kwargs,
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "temperature": kwargs.get("temperature", self.temperature),
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):  # SSE comment
                        continue
                    if line.startswith("data: "):
                        data = line[6:]
                    else:
                        data = line
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = obj["choices"][0]["delta"]
                        content = delta.get("content")
                    except (KeyError, IndexError):
                        continue
                    if content:
                        yield content
