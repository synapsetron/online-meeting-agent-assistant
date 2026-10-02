from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from server.models import TranscriptSegment

logger = logging.getLogger(__name__)


class ASRAdapter(ABC):
    on_segment: Callable[[TranscriptSegment], Awaitable[None]] | None = None

    @abstractmethod
    async def start(self, sample_rate: int) -> None: ...

    @abstractmethod
    async def feed_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...


class StubASRAdapter(ASRAdapter):
    async def start(self, sample_rate: int) -> None:
        pass

    async def feed_audio(self, chunk: bytes) -> None:
        pass

    async def stop(self) -> None:
        pass


class OpenAIRealtimeAdapter(ASRAdapter):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._running = False

    async def start(self, sample_rate: int) -> None:
        logger.info("OpenAIRealtimeAdapter starting (sample_rate=%d)", sample_rate)
        self._running = True
        # TODO: open WebSocket connection to OpenAI Realtime API
        # wss://api.openai.com/v1/realtime with auth header

    async def feed_audio(self, chunk: bytes) -> None:
        if not self._running:
            return
        # TODO: send audio chunk over the WebSocket as input_audio_buffer.append

    async def stop(self) -> None:
        logger.info("OpenAIRealtimeAdapter stopping")
        self._running = False
        # TODO: close WebSocket connection
