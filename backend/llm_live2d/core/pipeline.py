"""
llm_live2d.core.pipeline
========================

Pipeline 是整个框架的心脏。它把 LLM / Parser / Splitter / TTS / AudioSink 串起来，
对外暴露两个接口：
    pipeline.handle_user_message(text)  → 异步生成 Action 流
    pipeline.interrupt(turn_id)         → 打断正在进行的轮次

设计要点：
1. 每个用户输入对应一个 Turn。Turn 内部启动多个并发任务：
     - LLM 流式生成 + Parser 实时解析 → 产出 (str|Action) 流
     - SentenceSplitter 把纯文本聚合成整句
     - TTS Worker（独立任务）按句合成音频
2. Action 流是有序的：表情/动作 Action 立即吐出；say/audio Action 必须等 TTS 完成才能放出
   （否则前端会看到"先念后嘴动"的错位）。
3. 中断时：取消 LLM 任务、取消所有 pending TTS、给前端发 StopAction。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional

from .actions import (
    Action,
    AudioAction,
    ErrorAction,
    SayAction,
    StopAction,
    TurnEndAction,
    TurnStartAction,
)
from .parser import ActionParser
from .providers import AudioSink, ChatMessage, LLMProvider, TTSProvider
from .splitter import SentenceSplitter

log = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    system_prompt: str = (
        "你是一个 Live2D 虚拟形象。回复时可以在文本中插入控制标签：\n"
        "  [emotion:happy] / [emotion:sad] / [emotion:surprised] 切换表情\n"
        "  [motion:Wave] / [motion:TapBody] 触发动作\n"
        "  <think>...</think> 包裹内心独白（不会被朗读）\n"
        "保持回复自然，不要刻意大量使用标签。"
    )
    history_max_turns: int = 20
    tts_concurrency: int = 2  # 同时合成几句话（提高吞吐）


@dataclass
class _PendingSay:
    """LLM 已经产出、等待 TTS 完成的一句台词。"""
    say: SayAction
    audio_future: asyncio.Future  # 完成后是 (audio_url) 或 None（被取消）
    expressions: List[Action] = field(default_factory=list)  # 这句话之前的表情


class Pipeline:
    def __init__(
        self,
        llm: LLMProvider,
        tts: TTSProvider,
        sink: AudioSink,
        config: Optional[PipelineConfig] = None,
    ):
        self.llm = llm
        self.tts = tts
        self.sink = sink
        self.config = config or PipelineConfig()
        self._history: List[ChatMessage] = []
        self._current_turn: Optional["_Turn"] = None
        self._lock = asyncio.Lock()  # 防止并发触发两个 turn

    # ---------------- 公开 API ----------------

    async def handle_user_message(self, text: str) -> AsyncIterator[Action]:
        """
        处理一条用户消息，异步生成 Action 流。

        调用方应当在前端 socket 里 `async for action in pipeline.handle_user_message(...)`
        然后把每个 action 序列化发给前端。

        注意：同一个 Pipeline 实例不应并发调用此方法（一个会话同时只能有一个 turn）。
        """
        async with self._lock:
            turn = _Turn(self, text)
            self._current_turn = turn
            try:
                async for act in turn.run():
                    yield act
            finally:
                self._current_turn = None

    async def interrupt(self, turn_id: Optional[str] = None) -> bool:
        """
        打断当前 turn。turn_id 为 None 时打断任何正在进行的 turn。
        返回是否真的打断了某个 turn。
        """
        turn = self._current_turn
        if turn is None:
            return False
        if turn_id is not None and turn.turn_id != turn_id:
            return False
        await turn.cancel()
        return True

    def reset_history(self) -> None:
        self._history.clear()

    # ---------------- 内部：会话历史管理 ----------------

    def _build_messages(self, user_text: str) -> List[ChatMessage]:
        msgs = [ChatMessage(role="system", content=self.config.system_prompt)]
        # 截断到最近 N 轮
        history = self._history[-self.config.history_max_turns * 2 :]
        msgs.extend(history)
        msgs.append(ChatMessage(role="user", content=user_text))
        return msgs

    def _commit_turn(self, user_text: str, assistant_text: str) -> None:
        """轮次结束（或被打断）后写入历史。assistant_text 应是"实际说出口"的部分。"""
        self._history.append(ChatMessage(role="user", content=user_text))
        if assistant_text.strip():
            self._history.append(
                ChatMessage(role="assistant", content=assistant_text)
            )


class _Turn:
    """单轮对话的状态机。"""

    def __init__(self, pipeline: Pipeline, user_text: str):
        self.pipeline = pipeline
        self.user_text = user_text
        self.turn_id = f"t-{uuid.uuid4().hex[:8]}"
        self._cancelled = asyncio.Event()
        self._spoken_text: List[str] = []  # 记录"实际说出口"的台词
        self._raw_llm_text: str = ""  # 记录原始 LLM 返回（包含标签）
        self._llm_task: Optional[asyncio.Task] = None
        self._tts_tasks: List[asyncio.Task] = []
        # 缓存表情，等下一个句子一起发送
        self._pending_expressions: List[Action] = []
        # 串行通道：LLM/Parser 把"已经定下来的、待 TTS"的句子放进这里
        self._pending_q: asyncio.Queue[Optional[_PendingSay]] = asyncio.Queue()
        # 输出通道：所有要发给前端的 Action 都进这里
        self._out_q: asyncio.Queue[Optional[Action]] = asyncio.Queue()

    async def run(self) -> AsyncIterator[Action]:
        yield TurnStartAction(turn_id=self.turn_id)

        self._llm_task = asyncio.create_task(self._llm_loop(), name="llm-loop")
        emit_task = asyncio.create_task(self._emit_loop(), name="emit-loop")

        try:
            while True:
                act = await self._out_q.get()
                if act is None:
                    break
                yield act
        finally:
            # 兜底取消
            if self._llm_task and not self._llm_task.done():
                self._llm_task.cancel()
            for t in self._tts_tasks:
                if not t.done():
                    t.cancel()
            if not emit_task.done():
                emit_task.cancel()
            with contextlib.suppress(BaseException):
                await emit_task

            # 把这一轮写入历史（即使被中断，已说出口的部分也要留下）
            self.pipeline._commit_turn(
                self.user_text, "".join(self._spoken_text)
            )

        if self._cancelled.is_set():
            yield StopAction(turn_id=self.turn_id)
        yield TurnEndAction(turn_id=self.turn_id, raw_text=self._raw_llm_text)

    async def cancel(self) -> None:
        self._cancelled.set()
        if self._llm_task and not self._llm_task.done():
            self._llm_task.cancel()
        for t in self._tts_tasks:
            if not t.done():
                t.cancel()
        # 让 emit_loop 知道结束
        await self._pending_q.put(None)

    # ---------------- LLM + Parser 主循环 ----------------

    async def _llm_loop(self) -> None:
        parser = ActionParser()
        splitter = SentenceSplitter()
        messages = self.pipeline._build_messages(self.user_text)

        async def emit_text_chunks(items):
            """把 parser 产出的项目分流：Action → 缓存；str → splitter。"""
            for item in items:
                if self._cancelled.is_set():
                    return
                if isinstance(item, str):
                    sentences = splitter.feed(item)
                    for s in sentences:
                        await self._enqueue_say(s)
                else:
                    # Expression / Motion / Thinking 先缓存，等下一个句子一起发送
                    log.info(f"[Pipeline] 缓存表情/动作: {item}")
                    self._pending_expressions.append(item)

        try:
            stream = self.pipeline.llm.astream(messages)
            async for chunk in stream:
                if self._cancelled.is_set():
                    break
                self._raw_llm_text += chunk  # 记录原始返回
                items = list(parser.feed(chunk))
                await emit_text_chunks(items)

            if not self._cancelled.is_set():
                # flush parser 与 splitter 残余
                items = list(parser.flush())
                await emit_text_chunks(items)
                tail_sentences = splitter.flush()
                for s in tail_sentences:
                    await self._enqueue_say(s)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            log.exception("LLM loop error")
            await self._out_q.put(ErrorAction(message=str(e), code="llm"))
        finally:
            # 如果还有剩余表情（LLM 以表情结尾），直接发送
            for expr in self._pending_expressions:
                await self._out_q.put(expr)
            self._pending_expressions.clear()
            # 通知下游：LLM 结束了
            await self._pending_q.put(None)

    async def _enqueue_say(self, text: str) -> None:
        """为一句台词起一个 TTS 任务，并把 PendingSay 入队等待按序发送。"""
        say = SayAction(text=text)
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        # 把缓存的表情带上（不立即发送，等 TTS 完成后和音频一起发送）
        exprs = self._pending_expressions.copy()
        self._pending_expressions.clear()
        log.info(f"[Pipeline] 入队句子: '{text[:30]}...' 带着 {len(exprs)} 个表情")
        await self._pending_q.put(_PendingSay(say=say, audio_future=future, expressions=exprs))

        # 起一个 TTS 任务（受 concurrency 限制，简化起见用 semaphore）
        task = asyncio.create_task(self._tts_one(say, future), name=f"tts-{say.id}")
        self._tts_tasks.append(task)

    # ---------------- TTS Worker ----------------

    async def _tts_one(self, say: SayAction, future: asyncio.Future) -> None:
        # 简单的并发限制：用 pipeline 级 semaphore
        sem = _get_or_create_tts_sem(self.pipeline)
        async with sem:
            if self._cancelled.is_set():
                if not future.done():
                    future.set_result(None)
                return
            try:
                result = await self.pipeline.tts.synthesize(say.text)
                url = await self.pipeline.sink.put(result)
                if not future.done():
                    future.set_result(url)
            except asyncio.CancelledError:
                if not future.done():
                    future.set_result(None)
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("TTS error for say %s", say.id)
                if not future.done():
                    future.set_exception(e)

    # ---------------- 顺序发射 say + audio ----------------

    async def _emit_loop(self) -> None:
        """
        从 _pending_q 按序取 PendingSay：
          - 等其 audio future 完成
          - 发送 SayAction + AudioAction（表情信息放在 AudioAction 里）
        遇到 None 表示 LLM 结束，flush 完后给 out_q 发 None 让上层退出。
        """
        try:
            while True:
                item = await self._pending_q.get()
                if item is None:
                    break
                if self._cancelled.is_set():
                    continue
                # 等 TTS 完成
                try:
                    url = await item.audio_future
                except Exception as e:  # noqa: BLE001
                    log.warning("TTS failed for %s: %s", item.say.id, e)
                    # 即便 TTS 失败也把文字发出去，让用户看到回复
                    await self._out_q.put(item.say)
                    self._spoken_text.append(item.say.text)
                    continue
                if url is None:
                    # 被取消
                    continue
                # 发送 say 和 audio（表情信息放在 audio 里）
                await self._out_q.put(item.say)
                # 把表情信息序列化成 dict 列表
                exprs_data = [{"name": e.name, "hold_ms": e.hold_ms} for e in item.expressions]
                if exprs_data:
                    log.info(f"[Pipeline] 音频携带表情: {exprs_data}")
                await self._out_q.put(
                    AudioAction(url=url, say_id=item.say.id, expressions=exprs_data)
                )
                self._spoken_text.append(item.say.text)
        finally:
            await self._out_q.put(None)


def _get_or_create_tts_sem(pipeline: Pipeline) -> asyncio.Semaphore:
    sem = getattr(pipeline, "_tts_sem", None)
    if sem is None:
        sem = asyncio.Semaphore(pipeline.config.tts_concurrency)
        pipeline._tts_sem = sem  # type: ignore[attr-defined]
    return sem
