"""核心层：协议、Pipeline、抽象接口。无任何具体 provider 依赖。"""
from .actions import (
    Action,
    AudioAction,
    AudioPlaybackEnded,
    ErrorAction,
    ExpressionAction,
    InboundEvent,
    InterruptSignal,
    MotionAction,
    SayAction,
    StopAction,
    ThinkingAction,
    TurnEndAction,
    TurnStartAction,
    UserMessage,
    parse_inbound,
    serialize,
)
from .pipeline import Pipeline, PipelineConfig
from .providers import (
    AudioSink,
    ChatMessage,
    LLMProvider,
    TTSProvider,
    TTSResult,
)

__all__ = [
    # actions
    "Action", "SayAction", "AudioAction", "ExpressionAction", "MotionAction",
    "ThinkingAction", "TurnStartAction", "TurnEndAction", "StopAction", "ErrorAction",
    "InboundEvent", "UserMessage", "InterruptSignal", "AudioPlaybackEnded",
    "serialize", "parse_inbound",
    # providers
    "LLMProvider", "TTSProvider", "AudioSink", "ChatMessage", "TTSResult",
    # pipeline
    "Pipeline", "PipelineConfig",
]
