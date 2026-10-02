from __future__ import annotations

import pytest

from server.models import (
    AgendaItem,
    AgendaItemStatus,
    Hint,
    HintType,
    TranscriptSegment,
)
from server.core.state_store import MeetingStateStore
from server.agents.agenda_tracker import AgendaDelta


def make_segment(
    seg_id: str,
    text: str,
    *,
    meeting_id: str = "m-1",
    speaker_id: str = "s-1",
    timestamp: float = 0.0,
    is_final: bool = True,
) -> TranscriptSegment:
    return TranscriptSegment(
        id=seg_id,
        meeting_id=meeting_id,
        speaker_id=speaker_id,
        text=text,
        timestamp=timestamp,
        is_final=is_final,
    )


def make_agenda_items() -> list[AgendaItem]:
    return [
        AgendaItem(id="ag-1", title="Project overview", order=1, estimated_minutes=5),
        AgendaItem(id="ag-2", title="Architecture review", order=2, estimated_minutes=10),
        AgendaItem(id="ag-3", title="Timeline", order=3, estimated_minutes=5),
    ]


def _store() -> MeetingStateStore:
    return MeetingStateStore(
        meeting_id="m-1",
        agenda_items=make_agenda_items(),
        window_size=20,
    )


class TestAddSegmentAndGetWindow:
    def test_add_and_retrieve(self) -> None:
        store = _store()
        seg = make_segment("seg-1", "Hello world")
        store.add_segment(seg)
        window = store.get_window()
        assert len(window) == 1
        assert window[0].id == "seg-1"

    def test_window_returns_last_n(self) -> None:
        store = MeetingStateStore(
            meeting_id="m-1",
            agenda_items=make_agenda_items(),
            window_size=3,
        )
        for i in range(10):
            store.add_segment(
                make_segment(f"seg-{i}", f"text {i}", timestamp=float(i))
            )
        window = store.get_window()
        assert len(window) == 3
        assert window[0].id == "seg-7"
        assert window[2].id == "seg-9"

    def test_window_larger_than_segments(self) -> None:
        store = _store()
        store.add_segment(make_segment("seg-1", "only one"))
        window = store.get_window()
        assert len(window) == 1


class TestApplyAgendaDelta:
    def test_change_item_status(self) -> None:
        store = _store()
        delta = AgendaDelta(
            status_changes={"ag-1": AgendaItemStatus.ACTIVE},
            new_active_item_id="ag-1",
        )
        store.apply_agenda_delta(delta)
        matched = [item for item in store.agenda.items if item.id == "ag-1"]
        assert matched[0].status == AgendaItemStatus.ACTIVE
        assert store.agenda.active_item_id == "ag-1"

    def test_change_to_covered_with_evidence(self) -> None:
        store = _store()
        delta_activate = AgendaDelta(
            status_changes={"ag-1": AgendaItemStatus.ACTIVE},
            new_active_item_id="ag-1",
        )
        store.apply_agenda_delta(delta_activate)

        delta_cover = AgendaDelta(
            status_changes={"ag-1": AgendaItemStatus.COVERED},
            evidence_additions={"ag-1": ["seg-1", "seg-2"]},
        )
        store.apply_agenda_delta(delta_cover)

        matched = [item for item in store.agenda.items if item.id == "ag-1"]
        assert matched[0].status == AgendaItemStatus.COVERED
        assert "seg-1" in matched[0].evidence

    def test_elapsed_updates(self) -> None:
        store = _store()
        delta = AgendaDelta(elapsed_updates={"ag-1": 120.0})
        store.apply_agenda_delta(delta)
        matched = [item for item in store.agenda.items if item.id == "ag-1"]
        assert matched[0].elapsed_seconds == 120.0


class TestHints:
    def test_add_hint(self) -> None:
        store = _store()
        hint = Hint(
            id="h-1",
            type=HintType.AGENDA_SUGGESTION,
            agenda_item_id="ag-1",
            message="Consider next item",
            evidence_segment_ids=["seg-1"],
            confidence=0.9,
            timestamp=10.0,
        )
        store.add_hint(hint)
        snap = store.snapshot()
        assert len(snap["hints"]) == 1

    def test_dismiss_hint(self) -> None:
        store = _store()
        hint = Hint(
            id="h-1",
            type=HintType.TOPIC_DRIFT,
            agenda_item_id="ag-2",
            message="Off topic",
            evidence_segment_ids=[],
            confidence=0.7,
            timestamp=5.0,
        )
        store.add_hint(hint)
        result = store.dismiss_hint("h-1")
        assert result is True
        active = store.get_active_hints()
        assert len(active) == 0

    def test_dismiss_nonexistent_returns_false(self) -> None:
        store = _store()
        result = store.dismiss_hint("nonexistent")
        assert result is False


class TestIdRetrieval:
    def test_get_all_segment_ids(self) -> None:
        store = _store()
        store.add_segment(make_segment("seg-1", "a"))
        store.add_segment(make_segment("seg-2", "b"))
        ids = store.get_all_segment_ids()
        assert ids == {"seg-1", "seg-2"}

    def test_get_agenda_item_ids(self) -> None:
        store = _store()
        ids = store.get_agenda_item_ids()
        assert ids == {"ag-1", "ag-2", "ag-3"}


class TestSnapshot:
    def test_returns_serializable(self) -> None:
        store = _store()
        store.add_segment(make_segment("seg-1", "hello"))
        snap = store.snapshot()
        assert "meeting" in snap
        assert "agenda" in snap
        assert "hints" in snap
        assert "rolling_summary" in snap
        assert "transcript_window" in snap
        assert isinstance(snap["transcript_window"], list)
