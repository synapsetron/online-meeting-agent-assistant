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

    def test_match_without_signal_starts_item_when_none_active(self) -> None:
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
        assert delta.new_active_item_id == "ag-1"
        assert delta.status_changes.get("ag-1") == AgendaItemStatus.ACTIVE

    def test_switches_to_other_item_without_signal_when_active_not_mentioned(self) -> None:
        tracker = AgendaTracker()
        agenda = _agenda()
        agenda.items[0].status = AgendaItemStatus.ACTIVE
        agenda.active_item_id = "ag-1"
        analysis = TranscriptAnalysis(
            matched_agenda_item_ids=["ag-2"],
            is_transition_signal=False,
        )
        delta = tracker.track(agenda, analysis, "seg-1", 1010.0)
        assert delta.new_active_item_id == "ag-2"

    def test_no_switch_when_active_item_still_mentioned(self) -> None:
        tracker = AgendaTracker()
        agenda = _agenda()
        agenda.items[0].status = AgendaItemStatus.ACTIVE
        agenda.active_item_id = "ag-1"
        analysis = TranscriptAnalysis(
            matched_agenda_item_ids=["ag-1", "ag-2"],
            is_transition_signal=False,
        )
        delta = tracker.track(agenda, analysis, "seg-1", 1010.0)
        assert delta.new_active_item_id is None


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


class TestElapsedTime:
    def test_elapsed_is_per_item_and_handles_millisecond_timestamps(self) -> None:
        tracker = AgendaTracker()
        agenda = _agenda()
        t0 = 1_700_000_000_000.0  # epoch ms, as sent by the browser
        start = TranscriptAnalysis(matched_agenda_item_ids=["ag-1"])
        d1 = tracker.track(agenda, start, "s1", t0)
        assert d1.elapsed_updates["ag-1"] == 0.0
        agenda.items[0].status = AgendaItemStatus.ACTIVE
        agenda.active_item_id = "ag-1"
        d2 = tracker.track(agenda, TranscriptAnalysis(), "s2", t0 + 90_000)
        assert d2.elapsed_updates["ag-1"] == pytest.approx(90.0)
        # mentioning the active item again must not restart its timer
        d3 = tracker.track(agenda, start, "s3", t0 + 120_000)
        assert d3.elapsed_updates["ag-1"] == pytest.approx(120.0)
