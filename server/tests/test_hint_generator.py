from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from server.agents.hint_generator import HintGenerator
from server.config import Config
from server.core.circuit_breaker import CircuitState
from server.models import AgendaItem, AgendaItemStatus, AgendaState, TranscriptSegment


def _agenda() -> AgendaState:
    return AgendaState(
        items=[
            AgendaItem(id="ag-1", title="Topic A", order=1, estimated_minutes=5),
        ],
        start_time=0.0,
    )


def _segment(idx: int = 0) -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg-{idx}",
        meeting_id="m-1",
        speaker_id="s-1",
        text=f"text {idx}",
        timestamp=float(idx),
        is_final=True,
    )


class TestHintGeneratorCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_consecutive_failures(self) -> None:
        gen = HintGenerator(api_key="test", model="test", timeout=5.0)
        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(
            side_effect=Exception("API error")
        )

        for _ in range(3):
            result = await gen.generate(_agenda(), "", [_segment()])
            assert result == []

        assert gen._circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_skips_call_when_circuit_open(self) -> None:
        gen = HintGenerator(api_key="test", model="test", timeout=5.0)
        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(
            side_effect=Exception("API error")
        )

        # Open the circuit
        for _ in range(3):
            await gen.generate(_agenda(), "", [_segment()])

        # Reset the mock to verify no more calls are made
        gen._client.messages.create.reset_mock()
        result = await gen.generate(_agenda(), "", [_segment()])
        assert result == []
        gen._client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_closes_on_success(self) -> None:
        gen = HintGenerator(api_key="test", model="test", timeout=5.0)

        # Start with a successful call
        mock_block = type("Block", (), {"text": "[]"})()
        mock_response = type("Response", (), {"content": [mock_block]})()
        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(return_value=mock_response)

        result = await gen.generate(_agenda(), "", [_segment()])
        assert gen._circuit_breaker.state == CircuitState.CLOSED


class TestConfigModelId:
    def test_default_model_is_current(self) -> None:
        config = Config()
        assert config.anthropic_model == "claude-sonnet-5-5"
