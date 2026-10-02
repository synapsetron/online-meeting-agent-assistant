from __future__ import annotations

import time
from typing import TYPE_CHECKING

from server.models import (
    AgendaItem,
    AgendaItemStatus,
    AgendaState,
    CaptureState,
    Hint,
    MeetingInfo,
    MeetingStatus,
    TranscriptSegment,
)

if TYPE_CHECKING:
    from server.agents.agenda_tracker import AgendaDelta


class MeetingStateStore:
    def __init__(
        self,
        meeting_id: str,
        agenda_items: list[AgendaItem],
        window_size: int,
    ) -> None:
        self.meeting = MeetingInfo(
            id=meeting_id,
            title="",
            start_time=time.time(),
            status=MeetingStatus.CONNECTED,
            capture_state=CaptureState.IDLE,
        )
        self.agenda = AgendaState(
            items=[item.model_copy(deep=True) for item in agenda_items],
            start_time=time.time(),
        )
        self._all_segments: list[TranscriptSegment] = []
        self._hints: list[Hint] = []
        self._rolling_summary: str = ""
        self.window_size = window_size

    def add_segment(self, segment: TranscriptSegment) -> None:
        self._all_segments.append(segment)

    def get_window(self) -> list[TranscriptSegment]:
        final = [s for s in self._all_segments if s.is_final]
        return final[-self.window_size :]

    def get_rolling_summary(self) -> str:
        return self._rolling_summary

    def update_rolling_summary(self, summary: str) -> None:
        self._rolling_summary = summary

    def apply_agenda_delta(self, delta: AgendaDelta) -> None:
        items_by_id = {item.id: item for item in self.agenda.items}

        for item_id, new_status in delta.status_changes.items():
            if item_id in items_by_id:
                items_by_id[item_id].status = AgendaItemStatus(new_status)

        for item_id, segment_ids in delta.evidence_additions.items():
            if item_id in items_by_id:
                existing = set(items_by_id[item_id].evidence)
                for sid in segment_ids:
                    if sid not in existing:
                        items_by_id[item_id].evidence.append(sid)
                        existing.add(sid)

        for item_id, elapsed in delta.elapsed_updates.items():
            if item_id in items_by_id:
                items_by_id[item_id].elapsed_seconds = elapsed

        if delta.new_active_item_id is not None:
            self.agenda.active_item_id = delta.new_active_item_id

    def add_hint(self, hint: Hint) -> None:
        self._hints.append(hint)

    def dismiss_hint(self, hint_id: str) -> bool:
        for hint in self._hints:
            if hint.id == hint_id and not hint.dismissed:
                hint.dismissed = True
                return True
        return False

    def get_active_hints(self) -> list[Hint]:
        return [h for h in self._hints if not h.dismissed]

    def get_all_segment_ids(self) -> set[str]:
        return {s.id for s in self._all_segments}

    def get_agenda_item_ids(self) -> set[str]:
        return {item.id for item in self.agenda.items}

    def snapshot(self) -> dict:
        return {
            "meeting": self.meeting.model_dump(),
            "agenda": self.agenda.model_dump(),
            "hints": [h.model_dump() for h in self.get_active_hints()],
            "rolling_summary": self._rolling_summary,
            "transcript_window": [s.model_dump() for s in self.get_window()],
        }
