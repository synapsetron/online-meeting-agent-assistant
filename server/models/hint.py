from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class HintType(str, Enum):
    AGENDA_SUGGESTION = "agenda_suggestion"
    TOPIC_DRIFT = "topic_drift"
    TIME_WARNING = "time_warning"
    MISSED_ITEM = "missed_item"
    SUMMARY = "summary"


class Hint(BaseModel):
    id: str
    type: HintType
    agenda_item_id: str
    message: str
    evidence_segment_ids: list[str]
    confidence: float
    uncertainty: str | None = None
    timestamp: float
    dismissed: bool = False
