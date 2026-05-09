"""
llm_live2d.core.actions
=======================

Action 协议：后端送给前端的所有事件都是一个 Action。

设计原则：
- LLM 的原始文本（带情绪标签）只在后端流转。
- 前端只看 Action 流，不接触 LLM 原文。
- 任何新增的 Action 类型都应该在这里集中定义，便于前后端同步演进。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Literal, Optional, Union
import json
import uuid


def _new_id(prefix: str = "a") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@dataclass
class SayAction:
    """一段要朗读 + 显示的文本（一句话粒度）。"""
    text: str
    id: str = field(default_factory=lambda: _new_id("u"))
    type: Literal["say"] = "say"


@dataclass
class AudioAction:
    """指向一段已经合成好的音频。前端播放它，并由 lip-sync 驱动嘴部。"""
    url: str
    say_id: str  # 关联到对应的 SayAction，便于前端"边说边显示"
    expressions: List[dict] = field(default_factory=list)  # 这段音频对应的表情
    id: str = field(default_factory=lambda: _new_id("a"))
    type: Literal["audio"] = "audio"


@dataclass
class ExpressionAction:
    """切换 Live2D 表情。hold_ms=0 表示永久保持直到下一个表情。"""
    name: str
    hold_ms: int = 0
    type: Literal["expression"] = "expression"


@dataclass
class MotionAction:
    """触发一个 Live2D motion（动作）。"""
    group: str
    index: Optional[int] = None  # None = 该 group 中随机
    priority: int = 2  # 1=idle 2=normal 3=force
    type: Literal["motion"] = "motion"


@dataclass
class ThinkingAction:
    """AI 内心独白，前端可选择显示在小气泡里，不朗读。"""
    text: str
    type: Literal["thinking"] = "thinking"


@dataclass
class TurnStartAction:
    turn_id: str
    type: Literal["turn_start"] = "turn_start"


@dataclass
class TurnEndAction:
    turn_id: str
    raw_text: str = ""  # 原始 LLM 返回（包含标签）
    type: Literal["turn_end"] = "turn_end"


@dataclass
class StopAction:
    """通知前端立即停止当前正在播的音频与正在排队的 say/audio。"""
    turn_id: str
    type: Literal["stop"] = "stop"


@dataclass
class ErrorAction:
    message: str
    code: str = "internal"
    type: Literal["error"] = "error"


Action = Union[
    SayAction,
    AudioAction,
    ExpressionAction,
    MotionAction,
    ThinkingAction,
    TurnStartAction,
    TurnEndAction,
    StopAction,
    ErrorAction,
]


def serialize(action: Action) -> str:
    """把 Action 序列化成 JSON 字符串，准备发给前端。"""
    return json.dumps(asdict(action), ensure_ascii=False)


# --------- 入站事件（前端 → 后端） ---------
# 这些不是 Action，而是用户控制信号。单独定义。

@dataclass
class UserMessage:
    text: str
    type: Literal["user_message"] = "user_message"


@dataclass
class InterruptSignal:
    """用户打断 AI 当前发言。"""
    turn_id: str
    type: Literal["interrupt"] = "interrupt"


@dataclass
class AudioPlaybackEnded:
    """前端播放完一段音频后回报。可用于精确同步会话历史 truncation。"""
    audio_id: str
    say_id: str
    completed: bool  # 是否完整播完（False 表示被中断）
    type: Literal["audio_ended"] = "audio_ended"


InboundEvent = Union[UserMessage, InterruptSignal, AudioPlaybackEnded]


def parse_inbound(raw: str) -> InboundEvent:
    """把前端发来的 JSON 字符串解析成 InboundEvent。未知类型抛 ValueError。"""
    obj = json.loads(raw)
    t = obj.get("type")
    if t == "user_message":
        return UserMessage(text=obj["text"])
    if t == "interrupt":
        return InterruptSignal(turn_id=obj["turn_id"])
    if t == "audio_ended":
        return AudioPlaybackEnded(
            audio_id=obj["audio_id"],
            say_id=obj["say_id"],
            completed=bool(obj.get("completed", True)),
        )
    raise ValueError(f"unknown inbound type: {t!r}")
