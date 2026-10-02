from __future__ import annotations

import pytest

from server.models import AgendaItem, AgendaItemStatus, AgendaState
from server.agents.agenda_tracker import AgendaTracker, AgendaDelta
from server.agents.transcript_analyzer import TranscriptAnalysis


def _items() -> list[AgendaItem]:
    return [
        AgendaItem(id="ag-1", title="Project overview", order=1, estimated_minutes=5),
        AgendaItem(id="ag-2", title="Architecture review", order=2, estimated_minutes=10),
        AgendaItem(id="ag-3", title="Timeline", order=3, estimated_minutes=5),
    ]


def _agenda(**overrides: object) -> AgendaState:
    return AgendaState(items=_items(), start_time=1000.0, **overrides)  # type: ignore[arg-type]


class TestFirstItemActivation:
    def test_pending_to_active_on_transition(self) -> None:
        tracker = AgendaTracker()
        agenda = _agenda()
        analysis = TranscriptAnalysis(
            matched_agenda_item_ids=["ag-1"],
            is_transition_signal=True,
        )
        delta = tracker.track(
            agenda=agenda,
            analysis=analysis,
            segment_id="seg-1",
            current_time=1010.0,
        )
        assert delta.new_active_item_id == "ag-1"
        assert delta.status_changes.get("ag-1") == AgendaItemStatus.ACTIVE


class TestTransition:
    def test_active_to_covered_and_new_active(self) -> None:
        tracker = AgendaTracker()
        items = _items()
        items[0].status = AgendaItemStatus.ACTIVE
        items[0].evidence = ["seg-0"]
        agenda = AgendaState(
            items=items,
            active_item_id="ag-1",
            start_time=1000.0,
        )

        analysis = TranscriptAnalysis(
            matched_agenda_item_ids=["ag-2"],
            is_transition_signal=True,
        )
        delta = tracker.track(
            agenda=agenda,
            analysis=analysis,
            segment_id="seg-3",
            current_time=1300.0,
        )
        assert delta.status_changes.get("ag-1") == AgendaItemStatus.COVERED
        assert delta.status_changes.get("ag-2") == AgendaItemStatus.ACTIVE
        assert delta.new_active_item_id == "ag-2"

    def test_no_transition_without_signal(self) -> None:
        tracker = AgendaTracker()
        agenda = _agenda()
        analysis = TranscriptAnalysis(
            matched_agenda_item_ids=["ag-1"],
            is_transition_signal=False,
        )
        delta = tracker.track(
            agenda=agenda,
            analysis=analysis,
            segment_id="seg-1",
            current_time=1010.0,
        )
        assert delta.new_active_item_id is None
        assert "ag-1" not in delta.status_changes


class TestEvidenceTracking:
    def test_evidence_added_for_matched_items(self) -> None:
        tracker = AgendaTracker()
        agenda = _agenda()
        analysis = TranscriptAnalysis(
            matched_agenda_item_ids=["ag-1", "ag-2"],
            is_transition_signal=False,
        )
        delta = tracker.track(
            agenda=agenda,
            analysis=analysis,
            segment_id="seg-5",
            current_time=1050.0,
        )
        assert "seg-5" in delta.evidence_additions.get("ag-1", [])
        assert "seg-5" in delta.evidence_additions.get("ag-2", [])


class TestElapsedTime:
    def test_elapsed_tracked_for_active_item(self) -> None:
        tracker = AgendaTracker()
        items = _items()
        items[0].status = AgendaItemStatus.ACTIVE
        agenda = AgendaState(
            items=items,
            active_item_id="ag-1",
            start_time=1000.0,
        )

        analysis = TranscriptAnalysis()
        delta = tracker.track(
            agenda=agenda,
            analysis=analysis,
            segment_id="seg-10",
            current_time=1120.0,
        )
        assert "ag-1" in delta.elapsed_updates


class TestInvalidTransitions:
    def test_covered_item_cannot_become_active(self) -> None:
        tracker = AgendaTracker()
        items = _items()
        items[0].status = AgendaItemStatus.COVERED
        items[1].status = AgendaItemStatus.ACTIVE
        agenda = AgendaState(
            items=items,
            active_item_id="ag-2",
            start_time=1000.0,
        )

        analysis = TranscriptAnalysis(
            matched_agenda_item_ids=["ag-1"],
            is_transition_signal=True,
        )
        delta = tracker.track(
            agenda=agenda,
            analysis=analysis,
            segment_id="seg-20",
            current_time=2000.0,
        )
        assert delta.new_active_item_id is None
        assert "ag-1" not in delta.status_changes

    def test_no_match_produces_empty_delta(self) -> None:
        tracker = AgendaTracker()
        agenda = _agenda()
        analysis = TranscriptAnalysis()
        delta = tracker.track(
            agenda=agenda,
            analysis=analysis,
            segment_id="seg-1",
            current_time=1010.0,
        )
        assert delta.new_active_item_id is None
        assert len(delta.status_changes) == 0
        assert len(delta.evidence_additions) == 0
