"""
内存版 AudioSink。把 TTS 产物保存在进程内字典里，URL 形如 /audio/<id>.<ext>。

适合单机/开发场景。生产环境换成 S3/OSS sink 即可。
"""
from __future__ import annotations

import uuid
from typing import Dict, Optional

from ..core.providers import AudioSink, TTSResult


_MIME_TO_EXT = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}


class InMemoryAudioSink(AudioSink):
    """
    URL 路径前缀可在 Server 里挂载到一个 GET /audio/<id> 路由，
    路由实现里调 sink.get(audio_id)。
    """

    def __init__(self, url_prefix: str = "/audio"):
        self.url_prefix = url_prefix.rstrip("/")
        self._store: Dict[str, TTSResult] = {}

    async def put(self, audio: TTSResult) -> str:
        ext = _MIME_TO_EXT.get(audio.mime, "bin")
        audio_id = uuid.uuid4().hex
        key = f"{audio_id}.{ext}"
        self._store[key] = audio
        return f"{self.url_prefix}/{key}"

    async def get(self, audio_id: str) -> Optional[TTSResult]:
        return self._store.get(audio_id)

    def evict(self, audio_id: str) -> None:
        """主动释放某段音频的内存。前端 audio_ended 后可以触发。"""
        self._store.pop(audio_id, None)
