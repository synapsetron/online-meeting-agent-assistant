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


class AgendaTracker:
    def track(
        self,
        agenda: AgendaState,
        analysis: TranscriptAnalysis,
        segment_id: str,
        current_time: float,
    ) -> AgendaDelta:
        delta = AgendaDelta()

        if agenda.active_item_id:
            active_item = self._find_item(agenda, agenda.active_item_id)
            if active_item and agenda.start_time > 0:
                elapsed = active_item.elapsed_seconds + (
                    current_time - agenda.start_time
                    if active_item.elapsed_seconds == 0
                    else 0
                )
                delta.elapsed_updates[active_item.id] = elapsed

        for item_id in analysis.matched_agenda_item_ids:
            if item_id not in delta.evidence_additions:
                delta.evidence_additions[item_id] = []
            delta.evidence_additions[item_id].append(segment_id)

        if analysis.matched_agenda_item_ids and analysis.is_transition_signal:
            target_id = analysis.matched_agenda_item_ids[0]
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
