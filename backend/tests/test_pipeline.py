"""
端到端 Pipeline 测试（用 mock LLM/TTS，无需任何 API key）。

运行：
    cd backend
    python tests/test_pipeline.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_live2d.core import (
    AudioSink,
    ChatMessage,
    LLMProvider,
    Pipeline,
    PipelineConfig,
    TTSProvider,
    TTSResult,
)


class MockLLM(LLMProvider):
    name = "mock-llm"

    def __init__(self, script: str, chunk_size: int = 4):
        self.script = script
        self.chunk_size = chunk_size

    async def astream(self, messages, **kwargs):
        # 模拟流式：每隔 5ms 吐一小段
        for i in range(0, len(self.script), self.chunk_size):
            await asyncio.sleep(0.005)
            yield self.script[i : i + self.chunk_size]


class MockTTS(TTSProvider):
    name = "mock-tts"

    def __init__(self, latency_ms: int = 30):
        self.latency_ms = latency_ms
        self.calls = []

    async def synthesize(self, text: str, **kwargs):
        await asyncio.sleep(self.latency_ms / 1000)
        self.calls.append(text)
        # 假装产出 100 字节伪音频
        return TTSResult(
            audio_bytes=f"FAKE-AUDIO[{text}]".encode("utf-8"),
            mime="audio/mpeg",
        )


class DictSink(AudioSink):
    def __init__(self):
        self.store = {}
        self._n = 0

    async def put(self, audio):
        self._n += 1
        key = f"{self._n:04d}.mp3"
        self.store[key] = audio
        return f"/audio/{key}"

    async def get(self, key):
        return self.store.get(key)


async def test_basic_flow():
    print("=== test_basic_flow ===")
    script = (
        "[emotion:happy]你好呀！"
        "[motion:Wave]很高兴见到你。"
        "<think>对方挺开心的</think>"
        "需要我帮你做什么？"
    )
    llm = MockLLM(script, chunk_size=3)
    tts = MockTTS(latency_ms=20)
    sink = DictSink()
    pipeline = Pipeline(llm, tts, sink, PipelineConfig(tts_concurrency=2))

    actions = []
    async for act in pipeline.handle_user_message("你好"):
        actions.append(act)
        print(f"  {type(act).__name__}: {getattr(act, 'text', '') or getattr(act, 'name', '') or getattr(act, 'group', '') or getattr(act, 'turn_id', '')}")

    types = [type(a).__name__ for a in actions]
    print(f"\n  Types: {types}")
    print(f"  TTS called for: {tts.calls}")

    assert types[0] == "TurnStartAction"
    assert types[-1] == "TurnEndAction"
    assert "ExpressionAction" in types
    assert "MotionAction" in types
    assert "ThinkingAction" in types
    assert "SayAction" in types
    assert "AudioAction" in types

    # SayAction 数量应等于 TTS 被调用的次数
    say_count = sum(1 for t in types if t == "SayAction")
    audio_count = sum(1 for t in types if t == "AudioAction")
    assert say_count == audio_count == len(tts.calls), \
        f"say={say_count} audio={audio_count} tts={len(tts.calls)}"

    # 每个 say 都应该跟着对应的 audio
    sayings = [a for a in actions if type(a).__name__ in ("SayAction", "AudioAction")]
    for i in range(0, len(sayings), 2):
        s, a = sayings[i], sayings[i + 1]
        assert type(s).__name__ == "SayAction"
        assert type(a).__name__ == "AudioAction"
        assert a.say_id == s.id, "audio.say_id 必须对应 say.id"

    print("  PASS\n")


async def test_interrupt():
    print("=== test_interrupt ===")
    # 一个稍长的脚本，TTS 慢一点，便于在中间打断
    script = "第一句话。第二句话。第三句话。第四句话。第五句话。"
    llm = MockLLM(script, chunk_size=2)
    tts = MockTTS(latency_ms=100)
    sink = DictSink()
    pipeline = Pipeline(llm, tts, sink)

    actions = []

    async def consume():
        async for act in pipeline.handle_user_message("说点什么"):
            actions.append(act)

    consumer = asyncio.create_task(consume())
    # 等大约 250ms（够 LLM 生成几句、TTS 完成 1-2 句）后打断
    await asyncio.sleep(0.25)
    await pipeline.interrupt()
    await consumer

    types = [type(a).__name__ for a in actions]
    print(f"  Types: {types}")

    assert "StopAction" in types, "中断必须发出 StopAction"
    assert types[-1] == "TurnEndAction"

    # 历史里 assistant 的内容应只包含"实际说出口"的部分（即 SayAction.text 的累加）
    spoken = "".join(
        a.text for a in actions if type(a).__name__ == "SayAction"
    )
    print(f"  Spoken: {spoken!r}")
    print(f"  History: {[m.content for m in pipeline._history]}")
    if pipeline._history:
        assistant_msg = next(
            (m for m in pipeline._history if m.role == "assistant"), None
        )
        if assistant_msg:
            assert assistant_msg.content == spoken
    print("  PASS\n")


async def test_stream_split_across_tag():
    """测试 chunk 边界正好切在情绪标签中间的场景"""
    print("=== test_stream_split_across_tag ===")
    # 让 chunk_size 极小，标签必然被切碎
    script = "你好[emotion:happy]世界。再见[motion:Bow]朋友。"
    llm = MockLLM(script, chunk_size=2)  # 每 2 字一切
    tts = MockTTS(latency_ms=10)
    sink = DictSink()
    pipeline = Pipeline(llm, tts, sink)

    actions = []
    async for act in pipeline.handle_user_message("你好"):
        actions.append(act)

    expr_names = [a.name for a in actions if type(a).__name__ == "ExpressionAction"]
    motion_groups = [a.group for a in actions if type(a).__name__ == "MotionAction"]
    sayings = [a.text for a in actions if type(a).__name__ == "SayAction"]
    print(f"  Expressions: {expr_names}")
    print(f"  Motions:     {motion_groups}")
    print(f"  Sayings:     {sayings}")

    assert expr_names == ["happy"], f"Got {expr_names}"
    assert motion_groups == ["Bow"], f"Got {motion_groups}"
    # 台词不应有标签残留
    for s in sayings:
        assert "[" not in s and "<" not in s, f"Tag leaked into: {s!r}"
    print("  PASS\n")


async def main():
    await test_basic_flow()
    await test_interrupt()
    await test_stream_split_across_tag()
    print("ALL TESTS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
