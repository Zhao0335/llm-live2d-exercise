"""
llm_live2d.core.parser
======================

从 LLM 输出的文本中分离出"要朗读的内容"和"控制信号"。

约定（在 system prompt 里告诉 LLM）：
- [emotion:NAME]            插入一个表情切换，NAME 是 Live2D 模型里 expression 的名字
- [motion:GROUP]            插入一个动作，GROUP 是 motion group 的名字
- [motion:GROUP:INDEX]      指定 group 里第 INDEX 个动作
- <think>...</think>        内心独白，前端可以显示在思考气泡，但不朗读
- 其它文本一律视为要朗读的台词

例子：
    [emotion:happy]你好呀！[motion:Wave]很高兴见到你。<think>这个用户看起来很开心</think>

解析后产出：
    ExpressionAction(happy)
    "你好呀！"  → 进入句子流
    MotionAction(Wave)
    "很高兴见到你。"
    ThinkingAction("这个用户看起来很开心")
"""
from __future__ import annotations

from typing import Iterator, List, Tuple
import re

from .actions import (
    Action,
    ExpressionAction,
    MotionAction,
    ThinkingAction,
)


# 控制标签的正则。注意我们只匹配方括号里 [a-zA-Z0-9_:] 的内容，
# 避免误伤台词里的方括号（虽然中文回复里少见，但保险起见）
_TAG_RE = re.compile(
    r"\[(?P<kind>emotion|motion)"
    r":(?P<name>[a-zA-Z0-9_\-]+)"
    r"(?::(?P<idx>\d+))?\]"
)
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


class ActionParser:
    """
    流式解析器。

    用法：
        parser = ActionParser()
        for chunk in llm_stream:
            for item in parser.feed(chunk):
                # item 要么是 str（一段纯台词），要么是 Action（控制信号）
                ...
        for item in parser.flush():
            ...

    实现细节：
    - 维护一个文本缓冲区，遇到不完整的标签（比如 chunk 中途断在 "[em" 处）时不切。
    - <think>...</think> 内部的内容不参与朗读，整段作为 ThinkingAction 吐出。
    """

    def __init__(self):
        self._buf = ""
        self._in_thinking = False
        self._thinking_buf = ""

    def feed(self, chunk: str) -> Iterator[str | Action]:
        if not chunk:
            return
        self._buf += chunk
        yield from self._extract(force_flush=False)

    def flush(self) -> Iterator[str | Action]:
        yield from self._extract(force_flush=True)
        # 即使没有闭合的 </think> 也吐出去
        if self._thinking_buf.strip():
            yield ThinkingAction(text=self._thinking_buf.strip())
            self._thinking_buf = ""
        # 缓冲区残留作为台词吐出
        if self._buf:
            yield self._buf
            self._buf = ""

    # -------- 内部 --------

    def _extract(self, force_flush: bool) -> Iterator[str | Action]:
        """
        消费 self._buf，吐出能确定下来的 str / Action。
        没法确定的（可能是不完整的标签）保留在 buf 里等下一个 chunk。
        """
        while self._buf:
            if self._in_thinking:
                # 找闭合标签
                close_idx = self._buf.find(_THINK_CLOSE)
                if close_idx >= 0:
                    self._thinking_buf += self._buf[:close_idx]
                    self._buf = self._buf[close_idx + len(_THINK_CLOSE):]
                    self._in_thinking = False
                    if self._thinking_buf.strip():
                        yield ThinkingAction(text=self._thinking_buf.strip())
                    self._thinking_buf = ""
                    continue

                # 没找到完整 </think>。如果当前 buf 末尾可能是 </think> 的不完整前缀，
                # 就保留这部分等下一 chunk；其余先吞进 thinking_buf。
                if not force_flush:
                    partial = _find_partial_prefix(self._buf, _THINK_CLOSE)
                    if partial >= 0:
                        self._thinking_buf += self._buf[:partial]
                        self._buf = self._buf[partial:]
                        return
                # 全吃进 thinking_buf，等下一个 chunk
                self._thinking_buf += self._buf
                self._buf = ""
                return

            # 找最早的 "[" 或 "<think>" 起点。
            # 注意：流式场景下 chunk 可能在 "<thi" 这种不完整前缀处断开，
            # 不能简单地 find("<think>") —— 那样不完整前缀会被当作普通文本输出。
            bracket_idx = self._buf.find("[")
            think_idx = self._buf.find(_THINK_OPEN)
            partial_think_idx = -1 if force_flush else _find_partial_prefix(
                self._buf, _THINK_OPEN
            )
            candidates = [
                i for i in (bracket_idx, think_idx, partial_think_idx) if i >= 0
            ]
            if not candidates:
                # 整段都是纯台词
                yield self._buf
                self._buf = ""
                return

            next_special = min(candidates)
            if next_special > 0:
                yield self._buf[:next_special]
                self._buf = self._buf[next_special:]
                continue

            # 此时 buf 以 [ / <think> / <think> 的不完整前缀 开头
            if self._buf.startswith(_THINK_OPEN):
                self._buf = self._buf[len(_THINK_OPEN):]
                self._in_thinking = True
                continue

            # 不完整的 <think> 前缀：等下一 chunk
            if partial_think_idx == 0 and not self._buf.startswith("["):
                return

            # 以 [ 开头：尝试匹配标签
            m = _TAG_RE.match(self._buf)
            if m:
                kind = m.group("kind")
                name = m.group("name")
                idx_s = m.group("idx")
                if kind == "emotion":
                    yield ExpressionAction(name=name)
                else:  # motion
                    yield MotionAction(
                        group=name,
                        index=int(idx_s) if idx_s else None,
                    )
                self._buf = self._buf[m.end():]
                continue

            # 是 [ 开头但不是合法标签：可能是 chunk 中途断了，等更多数据
            # 但如果 force_flush，或缓冲区里这个 [ 后面已经看到 ] 还不匹配，
            # 那就当成普通字符吐出
            close_bracket = self._buf.find("]")
            if force_flush or (close_bracket >= 0 and close_bracket < 32):
                # 把这个 [ 当字面量吐出，后面继续解析
                yield self._buf[0]
                self._buf = self._buf[1:]
                continue
            # 否则等下一个 chunk
            return


def _find_partial_prefix(buf: str, target: str) -> int:
    """
    找 buf 里"target 不完整前缀"的起始位置：
    即 target 的某个非空前缀（不是 target 自己）正好是 buf 的尾子串。

    例：buf='hi <thi', target='<think>' → 返回 3（即 '<' 的位置）
        buf='hello',  target='<think>' → 返回 -1
        buf='<think>more', target='<think>' → 返回 -1（已是完整匹配，由别处处理）
    """
    n = len(target)
    # 检查长度从 n-1 到 1 的前缀
    max_check = min(n - 1, len(buf))
    for k in range(max_check, 0, -1):
        if buf.endswith(target[:k]):
            return len(buf) - k
    return -1
