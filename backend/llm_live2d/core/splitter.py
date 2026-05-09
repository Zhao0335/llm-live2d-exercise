"""
llm_live2d.core.splitter
========================

把流式 LLM 文本切成"可送 TTS 的整句"。

实现的核心问题：
- LLM 流式吐出的是 token，但 TTS 要的是句子。
- 不能等全部输出完才切，否则首句延迟很高。
- 也不能 token 级别送 TTS，那样 TTS 调用太碎。

策略：维护一个滚动缓冲区，每来一个 chunk 就检查能否切出新句。
切分依据：中文/英文的句末标点 + 换行。
"""
from __future__ import annotations

from typing import List
import re


# 中英文句末标点。冒号不切（"我跟你说：今天..."不该切）。
# 注意：分号也算句末，但若紧跟引号则不切（"他说：'走吧。'"中外层标点优先）
_END_PUNCT = "。！？!?．\n"
_SOFT_END_PUNCT = "；;"  # 较弱的切分点，仅在缓冲足够长时才切

# 缓冲区累积超过这个长度但仍没遇到句末时，强制按逗号切
_MAX_BUFFER_BEFORE_FORCE_SPLIT = 60
_FORCE_SPLIT_PUNCT = "，,、"

# 切出的句子至少要有这么多个字符，否则附加到下一句
# 防止 "好。" -> 单字句送 TTS 的浪费
_MIN_SENTENCE_LEN = 2


class SentenceSplitter:
    """
    用法：
        sp = SentenceSplitter()
        for chunk in stream:
            for sentence in sp.feed(chunk):
                tts.synthesize(sentence)
        for sentence in sp.flush():
            tts.synthesize(sentence)
    """

    def __init__(
        self,
        min_len: int = _MIN_SENTENCE_LEN,
        max_buffer: int = _MAX_BUFFER_BEFORE_FORCE_SPLIT,
    ):
        self._buf = ""
        self._min_len = min_len
        self._max_buffer = max_buffer

    def feed(self, chunk: str) -> List[str]:
        """喂入一段新文本，返回这次能切出的所有完整句子。"""
        if not chunk:
            return []
        self._buf += chunk
        return self._extract(force=False)

    def flush(self) -> List[str]:
        """流结束时调用，把缓冲区里剩余内容作为最后一句吐出来。"""
        out = self._extract(force=False)
        leftover = self._buf.strip()
        self._buf = ""
        if leftover:
            out.append(leftover)
        return out

    # -------- 内部 --------

    def _extract(self, force: bool) -> List[str]:
        sentences: List[str] = []
        while True:
            idx = self._find_split_index()
            if idx < 0:
                # 没找到硬切分点。看是否需要软切分（缓冲区过长）
                if len(self._buf) >= self._max_buffer:
                    soft_idx = self._find_soft_split_index()
                    if soft_idx >= 0:
                        s, rest = self._buf[: soft_idx + 1], self._buf[soft_idx + 1 :]
                        self._buf = rest
                        if len(s.strip()) >= self._min_len:
                            sentences.append(s.strip())
                        continue
                break

            s, rest = self._buf[: idx + 1], self._buf[idx + 1 :]
            self._buf = rest
            stripped = s.strip()
            if not stripped:
                continue
            if len(stripped) < self._min_len and sentences:
                # 太短的尾巴并到上一句（"……。哦。" 之类）
                sentences[-1] = sentences[-1] + stripped
            elif len(stripped) < self._min_len:
                # 没有上一句，且本句太短：暂存回缓冲区头部
                self._buf = stripped + self._buf
                break
            else:
                sentences.append(stripped)
        return sentences

    def _find_split_index(self) -> int:
        """找到 buf 里第一个硬切分点的下标。-1 表示没有。"""
        for i, ch in enumerate(self._buf):
            if ch in _END_PUNCT:
                return i
            if ch in _SOFT_END_PUNCT and i >= self._max_buffer // 2:
                return i
        return -1

    def _find_soft_split_index(self) -> int:
        # 在缓冲区后半段找一个逗号/顿号，作为退而求其次的切点
        half = len(self._buf) // 2
        for i in range(half, len(self._buf)):
            if self._buf[i] in _FORCE_SPLIT_PUNCT:
                return i
        return -1
