"""
WebSocket Server（基于 FastAPI / Starlette）。

接口：
    WS  /ws                  双向消息通道
    GET /audio/{key}         拉取已合成的 TTS 音频
    GET /health              健康检查

WS 协议：
    入站：UserMessage / InterruptSignal / AudioPlaybackEnded（见 core.actions）
    出站：Action（JSON 字符串）

把这一文件视为 Pipeline 的"传输层适配器"。要换 SSE / gRPC / Socket.IO，
照样写一份就行，业务层（Pipeline）一行不用改。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..core import (
    InterruptSignal,
    Pipeline,
    UserMessage,
    parse_inbound,
    serialize,
)
from ..providers.memory_sink import InMemoryAudioSink

log = logging.getLogger(__name__)


def create_app(
    pipeline_factory,
    sink: InMemoryAudioSink,
    *,
    cors_origins: Optional[list[str]] = None,
) -> FastAPI:
    """
    工厂函数：传入"如何创建一个 Pipeline"的可调用对象，返回 FastAPI app。

    pipeline_factory: () -> Pipeline
        每个新 WebSocket 连接调用一次，得到独立的 Pipeline 实例（独立会话历史）。
        如果想做多会话共享或持久化历史，在 factory 里自己处理。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("server up")
        yield
        log.info("server down")

    app = FastAPI(lifespan=lifespan)

    if cors_origins is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/health")
    async def _health():
        return {"ok": True}

    @app.get("/audio/{key}")
    async def _get_audio(key: str):
        result = await sink.get(key)
        if result is None:
            return Response(status_code=404)
        return Response(content=result.audio_bytes, media_type=result.mime)

    @app.websocket("/ws")
    async def _ws(websocket: WebSocket):
        await websocket.accept()
        pipeline = pipeline_factory()
        log.info("client connected")

        # turn 的执行任务（与 ws 的接收循环并行）
        current_task: Optional[asyncio.Task] = None

        async def run_turn(text: str):
            try:
                async for action in pipeline.handle_user_message(text):
                    await websocket.send_text(serialize(action))
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                log.exception("turn error")

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    event = parse_inbound(raw)
                except (ValueError, KeyError) as e:
                    log.warning("bad inbound message: %s (%s)", raw[:120], e)
                    continue

                if isinstance(event, UserMessage):
                    if current_task and not current_task.done():
                        # 用户在 AI 还没说完时又发了新消息：等同于隐式中断
                        await pipeline.interrupt()
                        with __import__("contextlib").suppress(BaseException):
                            await current_task
                    current_task = asyncio.create_task(run_turn(event.text))
                elif isinstance(event, InterruptSignal):
                    if current_task and not current_task.done():
                        await pipeline.interrupt(event.turn_id or None)
                # AudioPlaybackEnded 暂时只用作可选释放音频缓存
                else:
                    pass

        except WebSocketDisconnect:
            log.info("client disconnected")
        finally:
            if current_task and not current_task.done():
                await pipeline.interrupt()
                with __import__("contextlib").suppress(BaseException):
                    await current_task

    return app
