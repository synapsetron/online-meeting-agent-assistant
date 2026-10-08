from __future__ import annotations

from dataclasses import dataclass, field

from server.models import AgendaItemStatus, AgendaState
from server.agents.transcript_analyzer import TranscriptAnalysis


_VALID_TRANSITIONS: dict[AgendaItemStatus, set[AgendaItemStatus]] = {
    AgendaItemStatus.PENDING: {AgendaItemStatus.ACTIVE, AgendaItemStatus.SKIPPED},
    AgendaItemStatus.ACTIVE: {AgendaItemStatus.COVERED, AgendaItemStatus.DEFERRED},
}


@dataclass
class AgendaDelta:
    new_active_item_id: str | None = None
    status_changes: dict[str, AgendaItemStatus] = field(default_factory=dict)
    evidence_additions: dict[str, list[str]] = field(default_factory=dict)
    elapsed_updates: dict[str, float] = field(default_factory=dict)


def _to_seconds(timestamp: float) -> float:
    # Browser segments carry epoch milliseconds; the server clock is in seconds.
    return timestamp / 1000.0 if timestamp > 1e11 else timestamp


class AgendaTracker:
    def __init__(self) -> None:
        self._accumulated: dict[str, float] = {}
        self._active_since: dict[str, float] = {}

    def _elapsed(self, item_id: str, now: float) -> float:
        since = self._active_since.get(item_id)
        running = max(0.0, now - since) if since is not None else 0.0
        return self._accumulated.get(item_id, 0.0) + running

    def _start(self, agenda: AgendaState, item_id: str, now: float) -> None:
        if item_id in self._active_since:
            return
        item = self._find_item(agenda, item_id)
        if item and item_id not in self._accumulated:
            self._accumulated[item_id] = item.elapsed_seconds
        self._active_since[item_id] = now

    def _pause(self, item_id: str, now: float) -> None:
        if item_id in self._active_since:
            self._accumulated[item_id] = self._elapsed(item_id, now)
            del self._active_since[item_id]

    def track(
        self,
        agenda: AgendaState,
        analysis: TranscriptAnalysis,
        segment_id: str,
        current_time: float,
    ) -> AgendaDelta:
        delta = AgendaDelta()
        now = _to_seconds(current_time)

        for item_id in analysis.matched_agenda_item_ids:
            if item_id not in delta.evidence_additions:
                delta.evidence_additions[item_id] = []
            delta.evidence_additions[item_id].append(segment_id)

        # Start/switch when: explicit transition phrase, nothing active yet, or the
        # segment is about another item and no longer about the active one.
        active_id = agenda.active_item_id
        matched = analysis.matched_agenda_item_ids
        other_ids = [i for i in matched if i != active_id]
        drifted_to_other = bool(active_id) and active_id not in matched and bool(other_ids)
        can_start = analysis.is_transition_signal or not active_id or drifted_to_other
        if matched and can_start:
            target_id = other_ids[0] if other_ids else matched[0]
            target_item = self._find_item(agenda, target_id)

            if target_item and self._can_transition(
                target_item.status, AgendaItemStatus.ACTIVE
            ):
                if (
                    agenda.active_item_id
                    and agenda.active_item_id != target_id
                ):
                    prev_item = self._find_item(agenda, agenda.active_item_id)
                    if prev_item and self._can_transition(
                        prev_item.status, AgendaItemStatus.COVERED
                    ):
                        prev_evidence = prev_item.evidence + delta.evidence_additions.get(
                            prev_item.id, []
                        )
                        if prev_evidence:
                            delta.status_changes[prev_item.id] = (
                                AgendaItemStatus.COVERED
                            )

                delta.status_changes[target_id] = AgendaItemStatus.ACTIVE
                delta.new_active_item_id = target_id
                if agenda.active_item_id and agenda.active_item_id != target_id:
                    self._pause(agenda.active_item_id, now)
                self._start(agenda, target_id, now)

        running_id = delta.new_active_item_id or agenda.active_item_id
        if running_id:
            self._start(agenda, running_id, now)
            delta.elapsed_updates[running_id] = self._elapsed(running_id, now)

        return delta

    @staticmethod
    def _find_item(agenda: AgendaState, item_id: str):
        for item in agenda.items:
            if item.id == item_id:
                return item
        return None

    @staticmethod
    def _can_transition(
        current: AgendaItemStatus, target: AgendaItemStatus
    ) -> bool:
        return target in _VALID_TRANSITIONS.get(current, set())
