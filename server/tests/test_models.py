from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from server.models import (
    AgendaItem,
    AgendaItemStatus,
    AgendaState,
    CaptureState,
    ConnectMessage,
    DismissHintMessage,
    Hint,
    HintType,
    MeetingInfo,
    MeetingStatus,
    MeetingSummaryMessage,
    NewHintMessage,
    SessionAckMessage,
    Speaker,
    StateUpdateMessage,
    TranscriptSegment,
)
from server.models.messages import ClientMessage, ServerMessage


class TestAgendaItem:
    def test_create_and_serialize(self) -> None:
        item = AgendaItem(id="ag-1", title="Intro", order=1, estimated_minutes=5)
        data = item.model_dump()
        assert data["id"] == "ag-1"
        assert data["title"] == "Intro"
        assert data["order"] == 1
        assert data["estimated_minutes"] == 5
        assert data["status"] == "pending"
        assert data["elapsed_seconds"] == 0.0
        assert data["evidence"] == []

    def test_status_default(self) -> None:
        item = AgendaItem(id="x", title="X", order=0)
        assert item.status == AgendaItemStatus.PENDING

    def test_with_evidence(self) -> None:
        item = AgendaItem(
            id="ag-2",
            title="Review",
            order=2,
            evidence=["seg-1", "seg-2"],
        )
        assert len(item.evidence) == 2


class TestTranscriptSegment:
    def test_defaults(self) -> None:
        seg = TranscriptSegment(
            id="seg-1",
            meeting_id="m-1",
            speaker_id="s-1",
            text="hello",
            timestamp=100.0,
            is_final=True,
        )
        assert seg.is_final is True
        assert seg.confidence is None
        assert seg.version == 1

    def test_partial_segment(self) -> None:
        seg = TranscriptSegment(
            id="seg-2",
            meeting_id="m-1",
            speaker_id="s-1",
            text="hel",
            timestamp=100.0,
            is_final=False,
            confidence=0.7,
        )
        assert seg.is_final is False
        assert seg.confidence == 0.7


class TestHint:
    def test_all_fields(self) -> None:
        hint = Hint(
            id="h-1",
            type=HintType.AGENDA_SUGGESTION,
            agenda_item_id="ag-1",
            message="Consider moving to next item",
            evidence_segment_ids=["seg-1"],
            confidence=0.85,
            uncertainty="Speaker may return to this topic",
            timestamp=42.0,
        )
        data = hint.model_dump()
        assert data["id"] == "h-1"
        assert data["type"] == "agenda_suggestion"
        assert data["agenda_item_id"] == "ag-1"
        assert data["confidence"] == 0.85
        assert data["dismissed"] is False
        assert data["uncertainty"] == "Speaker may return to this topic"

    def test_dismissed_default(self) -> None:
        hint = Hint(
            id="h-2",
            type=HintType.TIME_WARNING,
            agenda_item_id="ag-1",
            message="Over time",
            evidence_segment_ids=[],
            confidence=1.0,
            timestamp=0.0,
        )
        assert hint.dismissed is False


class TestAgendaState:
    def test_multiple_items(self) -> None:
        items = [
            AgendaItem(id="ag-1", title="A", order=1),
            AgendaItem(id="ag-2", title="B", order=2),
            AgendaItem(id="ag-3", title="C", order=3),
        ]
        state = AgendaState(items=items)
        assert len(state.items) == 3
        assert state.active_item_id is None
        assert state.start_time == 0.0

    def test_with_active_item(self) -> None:
        items = [
            AgendaItem(id="ag-1", title="A", order=1, status=AgendaItemStatus.ACTIVE),
        ]
        state = AgendaState(items=items, active_item_id="ag-1")
        assert state.active_item_id == "ag-1"


class TestClientMessageDiscriminator:
    adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)

    def test_parse_connect(self) -> None:
        raw = {
            "type": "CONNECT",
            "meeting_id": "m-1",
            "title": "Standup",
            "agenda_items": [{"id": "ag-1", "title": "Updates", "order": 1}],
        }
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, ConnectMessage)
        assert msg.meeting_id == "m-1"
        assert len(msg.agenda_items) == 1

    def test_parse_dismiss_hint(self) -> None:
        raw = {"type": "DISMISS_HINT", "hint_id": "h-42"}
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, DismissHintMessage)
        assert msg.hint_id == "h-42"

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(Exception):
            self.adapter.validate_python({"type": "BOGUS"})


class TestServerMessageDiscriminator:
    adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)

    def test_parse_session_ack(self) -> None:
        raw = {"type": "SESSION_ACK", "session_id": "s-1"}
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, SessionAckMessage)
        assert msg.session_id == "s-1"

    def test_parse_state_update(self) -> None:
        raw = {
            "type": "STATE_UPDATE",
            "meeting": {
                "id": "m-1",
                "title": "T",
                "start_time": 0.0,
            },
            "agenda": {"items": []},
        }
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, StateUpdateMessage)

    def test_parse_meeting_summary(self) -> None:
        raw = {
            "type": "MEETING_SUMMARY",
            "summary": "All items covered.",
            "covered_items": ["ag-1"],
            "missed_items": ["ag-3"],
        }
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, MeetingSummaryMessage)
        assert msg.covered_items == ["ag-1"]

    def test_parse_new_hint(self) -> None:
        raw = {
            "type": "NEW_HINT",
            "hint": {
                "id": "h-1",
                "type": "topic_drift",
                "agenda_item_id": "ag-1",
                "message": "Off topic",
                "evidence_segment_ids": ["seg-1"],
                "confidence": 0.9,
                "timestamp": 10.0,
            },
        }
        msg = self.adapter.validate_python(raw)
        assert isinstance(msg, NewHintMessage)
        assert msg.hint.type == HintType.TOPIC_DRIFT
