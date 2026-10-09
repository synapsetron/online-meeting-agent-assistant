from __future__ import annotations

from dataclasses import dataclass, field

from server.models import AgendaItemStatus, AgendaState
from server.agents.transcript_analyzer import TranscriptAnalysis


_VALID_TRANSITIONS: dict[AgendaItemStatus, set[AgendaItemStatus]] = {
    AgendaItemStatus.PENDING: {AgendaItemStatus.ACTIVE, AgendaItemStatus.SKIPPED},
    AgendaItemStatus.ACTIVE: {AgendaItemStatus.COVERED, AgendaItemStatus.DEFERRED},
    # A topic that was left without evidence can be returned to.
    AgendaItemStatus.DEFERRED: {AgendaItemStatus.ACTIVE},
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
            self._switch(agenda, delta, target_id, now)

        running_id = delta.new_active_item_id or agenda.active_item_id
        if running_id:
            self._start(agenda, running_id, now)
            delta.elapsed_updates[running_id] = self._elapsed(running_id, now)

        return delta

    def activate(
        self,
        agenda: AgendaState,
        target_id: str,
        evidence_segment_ids: list[str],
        current_time: float,
    ) -> AgendaDelta:
        """Apply a switch proposed from outside the keyword rules (the LLM's
        semantic judgement). The same state machine and evidence rules apply;
        an empty delta means the proposal was not applicable."""
        delta = AgendaDelta()
        if not evidence_segment_ids or target_id == agenda.active_item_id:
            return delta
        now = _to_seconds(current_time)
        delta.evidence_additions[target_id] = list(evidence_segment_ids)
        if not self._switch(agenda, delta, target_id, now):
            return AgendaDelta()
        delta.elapsed_updates[target_id] = self._elapsed(target_id, now)
        return delta

    def _switch(
        self, agenda: AgendaState, delta: AgendaDelta, target_id: str, now: float
    ) -> bool:
        """Make *target_id* the active item, closing the previous one. An item
        left with transcript evidence becomes covered; one without evidence is
        deferred, never marked complete."""
        target_item = self._find_item(agenda, target_id)
        if not target_item or not self._can_transition(
            target_item.status, AgendaItemStatus.ACTIVE
        ):
            return False

        previous_id = agenda.active_item_id
        if previous_id and previous_id != target_id:
            prev_item = self._find_item(agenda, previous_id)
            if prev_item and prev_item.status == AgendaItemStatus.ACTIVE:
                has_evidence = bool(
                    prev_item.evidence + delta.evidence_additions.get(prev_item.id, [])
                )
                delta.status_changes[prev_item.id] = (
                    AgendaItemStatus.COVERED if has_evidence else AgendaItemStatus.DEFERRED
                )
            self._pause(previous_id, now)

        delta.status_changes[target_id] = AgendaItemStatus.ACTIVE
        delta.new_active_item_id = target_id
        self._start(agenda, target_id, now)
        return True

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
