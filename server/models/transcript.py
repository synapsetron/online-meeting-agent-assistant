from __future__ import annotations

from .base import CamelModel


class Speaker(CamelModel):
    id: str
    name: str
    color: str = "#888888"


class TranscriptSegment(CamelModel):
    id: str
    meeting_id: str
    speaker_id: str
    text: str
    timestamp: float
    is_final: bool
    confidence: float | None = None
    version: int = 1
