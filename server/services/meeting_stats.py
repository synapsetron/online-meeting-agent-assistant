from __future__ import annotations

import time
from typing import TYPE_CHECKING

from server.models.summary import AgendaItemStats, MeetingStats, SpeakerStats

if TYPE_CHECKING:
    from server.core.state_store import MeetingStateStore

OFF_AGENDA_TITLE = "Outside the agenda"


def _share(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def compute_meeting_stats(state: MeetingStateStore, now: float | None = None) -> MeetingStats:
    """Deterministic end-of-meeting statistics from the session state (no LLM).

    Speaking share is measured in transcribed words, not audio seconds: the
    backend receives text only, so word counts are the honest unit here.
    """
    segments = state.get_final_segments()
    words_of = {seg.id: len(seg.text.split()) for seg in segments}
    total_words = sum(words_of.values())

    by_speaker: dict[str, list[int]] = {}
    by_item: dict[str | None, list[int]] = {}
    for seg in segments:
        words = words_of[seg.id]
        speaker = by_speaker.setdefault(seg.speaker_id, [0, 0])
        speaker[0] += 1
        speaker[1] += words
        item = by_item.setdefault(state.get_segment_item(seg.id), [0, 0])
        item[0] += 1
        item[1] += words

    speakers = sorted(
        (
            SpeakerStats(speaker_id=sid, segments=n, words=w, share=_share(w, total_words))
            for sid, (n, w) in by_speaker.items()
        ),
        key=lambda s: s.words,
        reverse=True,
    )

    agenda = [
        AgendaItemStats(
            item_id=item.id,
            title=item.title,
            status=item.status.value,
            elapsed_seconds=round(item.elapsed_seconds, 1),
            estimated_minutes=item.estimated_minutes,
            segments=by_item.get(item.id, [0, 0])[0],
            words=by_item.get(item.id, [0, 0])[1],
            share=_share(by_item.get(item.id, [0, 0])[1], total_words),
        )
        for item in state.agenda.items
    ]
    if None in by_item:
        n, w = by_item[None]
        agenda.append(
            AgendaItemStats(
                item_id=None, title=OFF_AGENDA_TITLE, status="none", elapsed_seconds=0.0,
                segments=n, words=w, share=_share(w, total_words),
            )
        )

    end = time.time() if now is None else now
    return MeetingStats(
        duration_seconds=round(max(0.0, end - state.meeting.start_time), 1),
        final_segments=len(segments),
        total_words=total_words,
        speakers=speakers,
        agenda=agenda,
        hints_shown=state.hint_count,
    )
