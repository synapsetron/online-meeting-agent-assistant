from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from server.agents.orchestrator import Orchestrator

_SUMMARY_INTERVAL = 10
from server.config import Config
from server.core.state_store import MeetingStateStore
from server.models import AgendaItem, TranscriptSegment


def _make_config() -> Config:
    return Config(
        anthropic_api_key="test-key",
        llm_debounce_seconds=0.0,
        llm_min_new_words=0,
        summary_interval=_SUMMARY_INTERVAL,
        llm_flush_idle_seconds=0.0,
    )


def _make_store() -> MeetingStateStore:
    items = [
        AgendaItem(id="ag-1", title="Topic A", order=1, estimated_minutes=5),
    ]
    return MeetingStateStore(meeting_id="m-1", agenda_items=items, window_size=50)


def _final_segment(idx: int) -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg-{idx}",
        meeting_id="m-1",
        speaker_id="s-1",
        text=f"segment text {idx}",
        timestamp=float(idx),
        is_final=True,
    )


class TestRollingSummaryIntegration:
    @pytest.mark.asyncio
    async def test_summary_called_after_n_segments(self) -> None:
        """After _SUMMARY_INTERVAL final segments the orchestrator should
        kick off a background summary update via summarize_segments."""
        config = _make_config()
        orch = Orchestrator(config)
        store = _make_store()

        mock_summarize = AsyncMock(return_value="Updated summary text")
        mock_generate = AsyncMock(return_value=[])

        with (
            patch.object(orch._hint_gen, "summarize_segments", mock_summarize),
            patch.object(orch._hint_gen, "generate", mock_generate),
        ):
            for i in range(_SUMMARY_INTERVAL):
                await orch.process_segment(_final_segment(i), store)

            # Let the background task complete
            if orch._summary_task is not None:
                await orch._summary_task
            # Hint calls run in the background: wait for the one in flight.
            await orch.drain()
            await orch.aclose()

        mock_summarize.assert_called_once()
        assert store.get_rolling_summary() == "Updated summary text"

    @pytest.mark.asyncio
    async def test_no_summary_before_interval(self) -> None:
        """Before reaching the interval, no summary should be triggered."""
        config = _make_config()
        orch = Orchestrator(config)
        store = _make_store()

        mock_summarize = AsyncMock(return_value="summary")
        mock_generate = AsyncMock(return_value=[])

        with (
            patch.object(orch._hint_gen, "summarize_segments", mock_summarize),
            patch.object(orch._hint_gen, "generate", mock_generate),
        ):
            for i in range(_SUMMARY_INTERVAL - 1):
                await orch.process_segment(_final_segment(i), store)
            await orch.drain()
            await orch.aclose()

        mock_summarize.assert_not_called()
        assert store.get_rolling_summary() == ""

    @pytest.mark.asyncio
    async def test_summary_receives_buffered_segments(self) -> None:
        """The summarize call should receive the segments accumulated
        since the last summary."""
        config = _make_config()
        orch = Orchestrator(config)
        store = _make_store()

        captured_segments: list[TranscriptSegment] = []

        async def capture_summarize(
            current_summary: str,
            new_segments: list[TranscriptSegment],
        ) -> str:
            captured_segments.extend(new_segments)
            return "captured"

        mock_generate = AsyncMock(return_value=[])

        with (
            patch.object(
                orch._hint_gen, "summarize_segments", side_effect=capture_summarize
            ),
            patch.object(orch._hint_gen, "generate", mock_generate),
        ):
            for i in range(_SUMMARY_INTERVAL):
                await orch.process_segment(_final_segment(i), store)

            if orch._summary_task is not None:
                await orch._summary_task
            await orch.drain()
            await orch.aclose()

        assert len(captured_segments) == _SUMMARY_INTERVAL
        ids = [s.id for s in captured_segments]
        assert ids == [f"seg-{i}" for i in range(_SUMMARY_INTERVAL)]


class TestSummarizeSegmentsMethod:
    @pytest.mark.asyncio
    async def test_returns_current_summary_when_no_client(self) -> None:
        """When the anthropic client is unavailable, the method should
        return the existing summary unchanged."""
        from server.agents.hint_generator import HintGenerator

        gen = HintGenerator(api_key="", model="test", timeout=5.0)
        gen._client = None

        result = await gen.summarize_segments("existing", [_final_segment(0)])
        assert result == "existing"

    @pytest.mark.asyncio
    async def test_returns_updated_summary_on_success(self) -> None:
        from server.agents.hint_generator import HintGenerator

        gen = HintGenerator(api_key="test", model="test", timeout=5.0)

        mock_block = type("Block", (), {"text": "New comprehensive summary"})()
        mock_response = type("Response", (), {"content": [mock_block]})()

        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(return_value=mock_response)

        result = await gen.summarize_segments("old summary", [_final_segment(0)])
        assert result == "New comprehensive summary"

    @pytest.mark.asyncio
    async def test_returns_current_on_api_error(self) -> None:
        from server.agents.hint_generator import HintGenerator

        gen = HintGenerator(api_key="test", model="test", timeout=5.0)
        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(
            side_effect=Exception("API timeout")
        )

        result = await gen.summarize_segments("keep me", [_final_segment(0)])
        assert result == "keep me"
