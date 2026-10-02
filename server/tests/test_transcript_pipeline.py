from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import TypeAdapter, ValidationError

from server.config import Config
from server.models import (
    AgendaItem,
    AgendaItemStatus,
    Hint,
    HintType,
    TranscriptSegment,
)
from server.models.messages import (
    ClientMessage,
    StateUpdateMessage,
    TranscriptErrorMessage,
    TranscriptMessage,
)
from server.agents.orchestrator import Orchestrator, OrchestratorResult
from server.core.state_store import MeetingStateStore


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------


class TestTranscriptMessageModel:
    adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)

    def test_parse_transcript_message(self) -> None:
        raw = {
            "type": "TRANSCRIPT",
            "segment": {
                "id": "seg-1",
                "meeting_id": "m-1",
                "speaker_id": "s-1",
                "text": "Let us start with the budget review.",
                "timestamp": 100.0,
                "is_final": True,
            },
        }
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, TranscriptMessage)
        assert msg.segment.id == "seg-1"
        assert msg.segment.is_final is True
        assert msg.segment.text == "Let us start with the budget review."

    def test_parse_partial_segment(self) -> None:
        raw = {
            "type": "TRANSCRIPT",
            "segment": {
                "id": "seg-2",
                "meeting_id": "m-1",
                "speaker_id": "s-1",
                "text": "Let us st",
                "timestamp": 99.0,
                "is_final": False,
                "confidence": 0.6,
            },
        }
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, TranscriptMessage)
        assert msg.segment.is_final is False
        assert msg.segment.confidence == 0.6

    def test_missing_segment_field_raises(self) -> None:
        raw = {"type": "TRANSCRIPT"}
        with pytest.raises(ValidationError):
            self.adapter.validate_python(raw)

    def test_invalid_segment_raises(self) -> None:
        raw = {
            "type": "TRANSCRIPT",
            "segment": {"id": "seg-x"},  # missing required fields
        }
        with pytest.raises(ValidationError):
            self.adapter.validate_python(raw)


class TestTranscriptErrorMessageModel:
    def test_create_with_segment_id(self) -> None:
        msg = TranscriptErrorMessage(error="bad segment", segment_id="seg-7")
        data = msg.model_dump()
        assert data["type"] == "TRANSCRIPT_ERROR"
        assert data["error"] == "bad segment"
        assert data["segment_id"] == "seg-7"

    def test_create_without_segment_id(self) -> None:
        msg = TranscriptErrorMessage(error="missing field")
        assert msg.segment_id is None

    def test_roundtrip(self) -> None:
        msg = TranscriptErrorMessage(error="oops", segment_id="seg-3")
        restored = TranscriptErrorMessage.model_validate(msg.model_dump())
        assert restored.error == "oops"
        assert restored.segment_id == "seg-3"


class TestStateUpdateMessageExtended:
    def test_includes_hints_and_transcript(self) -> None:
        hint = Hint(
            id="h-1",
            type=HintType.TIME_WARNING,
            agenda_item_id="ag-1",
            message="Over time",
            evidence_segment_ids=["seg-1"],
            confidence=1.0,
            timestamp=100.0,
        )
        seg = TranscriptSegment(
            id="seg-1",
            meeting_id="m-1",
            speaker_id="s-1",
            text="hello",
            timestamp=100.0,
            is_final=True,
        )
        from server.models import MeetingInfo, AgendaState

        msg = StateUpdateMessage(
            meeting=MeetingInfo(id="m-1", title="T", start_time=0.0),
            agenda=AgendaState(items=[]),
            hints=[hint],
            recent_transcript=[seg],
        )
        data = msg.model_dump()
        assert len(data["hints"]) == 1
        assert data["hints"][0]["id"] == "h-1"
        assert len(data["recent_transcript"]) == 1
        assert data["recent_transcript"][0]["id"] == "seg-1"

    def test_defaults_empty(self) -> None:
        from server.models import MeetingInfo, AgendaState

        msg = StateUpdateMessage(
            meeting=MeetingInfo(id="m-1", title="T", start_time=0.0),
            agenda=AgendaState(items=[]),
        )
        assert msg.hints == []
        assert msg.recent_transcript == []


# ---------------------------------------------------------------------------
# Orchestrator end-to-end tests
# ---------------------------------------------------------------------------


def _make_config() -> Config:
    return Config(
        anthropic_api_key="test-key",
        llm_debounce_seconds=0.0,
        llm_timeout_seconds=5.0,
    )


def _make_state(items: list[AgendaItem] | None = None) -> MeetingStateStore:
    if items is None:
        items = [
            AgendaItem(id="ag-1", title="Budget review", order=1, estimated_minutes=5),
            AgendaItem(id="ag-2", title="Team updates", order=2, estimated_minutes=10),
        ]
    return MeetingStateStore(
        meeting_id="m-1",
        agenda_items=items,
        window_size=20,
    )


def _make_segment(
    seg_id: str = "seg-1",
    text: str = "Hello world",
    is_final: bool = True,
    timestamp: float = 100.0,
) -> TranscriptSegment:
    return TranscriptSegment(
        id=seg_id,
        meeting_id="m-1",
        speaker_id="s-1",
        text=text,
        timestamp=timestamp,
        is_final=is_final,
    )


class TestOrchestratorProcessSegment:
    @pytest.mark.asyncio
    async def test_partial_segment_returns_empty_result(self) -> None:
        config = _make_config()
        orchestrator = Orchestrator(config)
        state = _make_state()

        segment = _make_segment(is_final=False, text="Let us talk about")
        result = await orchestrator.process_segment(segment, state)

        assert isinstance(result, OrchestratorResult)
        assert result.agenda_delta is None
        assert result.hints == []
        assert result.time_warnings == []

    @pytest.mark.asyncio
    async def test_final_segment_produces_delta(self) -> None:
        config = _make_config()
        orchestrator = Orchestrator(config)
        state = _make_state()

        segment = _make_segment(text="Let us start with the budget review")
        result = await orchestrator.process_segment(segment, state)

        assert isinstance(result, OrchestratorResult)
        assert result.agenda_delta is not None

    @pytest.mark.asyncio
    async def test_segment_stored_in_state(self) -> None:
        config = _make_config()
        orchestrator = Orchestrator(config)
        state = _make_state()

        partial = _make_segment(seg_id="seg-p", is_final=False, text="Hel")
        await orchestrator.process_segment(partial, state)

        final = _make_segment(seg_id="seg-f", is_final=True, text="Hello")
        await orchestrator.process_segment(final, state)

        all_ids = state.get_all_segment_ids()
        assert "seg-p" in all_ids
        assert "seg-f" in all_ids

    @pytest.mark.asyncio
    async def test_multiple_segments_accumulate(self) -> None:
        config = _make_config()
        orchestrator = Orchestrator(config)
        state = _make_state()

        for i in range(5):
            seg = _make_segment(
                seg_id=f"seg-{i}",
                text=f"Discussion point {i}",
                timestamp=100.0 + i,
            )
            await orchestrator.process_segment(seg, state)

        window = state.get_window()
        assert len(window) == 5

    @pytest.mark.asyncio
    async def test_time_warning_for_overtime_item(self) -> None:
        config = _make_config()
        orchestrator = Orchestrator(config)

        items = [
            AgendaItem(
                id="ag-1",
                title="Quick item",
                order=1,
                estimated_minutes=1,
                status=AgendaItemStatus.ACTIVE,
                elapsed_seconds=120,  # 2 min, well over 1 min * 1.5
            ),
        ]
        state = _make_state(items)
        state.agenda.active_item_id = "ag-1"

        segment = _make_segment(text="Continuing the discussion")
        result = await orchestrator.process_segment(segment, state)

        assert len(result.time_warnings) >= 1
        warning = result.time_warnings[0]
        assert warning.type == HintType.TIME_WARNING
        assert warning.agenda_item_id == "ag-1"

    @pytest.mark.asyncio
    async def test_no_time_warning_for_on_schedule_item(self) -> None:
        config = _make_config()
        orchestrator = Orchestrator(config)

        items = [
            AgendaItem(
                id="ag-1",
                title="Normal item",
                order=1,
                estimated_minutes=10,
                status=AgendaItemStatus.ACTIVE,
                elapsed_seconds=5,
            ),
        ]
        state = _make_state(items)
        state.agenda.active_item_id = "ag-1"

        segment = _make_segment(text="On topic discussion")
        result = await orchestrator.process_segment(segment, state)

        assert result.time_warnings == []
