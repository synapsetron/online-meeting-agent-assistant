from __future__ import annotations

import re
from typing import TYPE_CHECKING

from server.models import Hint

if TYPE_CHECKING:
    from server.agents.agenda_tracker import AgendaDelta

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_TEXT_LENGTH = 10_000


def validate_hint(
    hint: Hint,
    valid_agenda_ids: set[str],
    valid_segment_ids: set[str],
) -> Hint | None:
    if hint.agenda_item_id not in valid_agenda_ids:
        return None
    if not all(sid in valid_segment_ids for sid in hint.evidence_segment_ids):
        return None
    if not 0.0 <= hint.confidence <= 1.0:
        return None
    return hint


def validate_agenda_delta(
    delta: AgendaDelta,
    valid_item_ids: set[str],
) -> AgendaDelta:
    delta.status_changes = {
        k: v for k, v in delta.status_changes.items() if k in valid_item_ids
    }
    delta.evidence_additions = {
        k: v for k, v in delta.evidence_additions.items() if k in valid_item_ids
    }
    delta.elapsed_updates = {
        k: v for k, v in delta.elapsed_updates.items() if k in valid_item_ids
    }
    if delta.new_active_item_id is not None and delta.new_active_item_id not in valid_item_ids:
        delta.new_active_item_id = None
    return delta


def sanitize_transcript_text(text: str) -> str:
    text = _CONTROL_CHARS.sub("", text)
    return text[:_MAX_TEXT_LENGTH]
