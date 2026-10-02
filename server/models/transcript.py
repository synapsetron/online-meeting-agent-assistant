from __future__ import annotations

from pydantic import BaseModel


class Speaker(BaseModel):
    id: str
    name: str
    color: str = "#888888"


class TranscriptSegment(BaseModel):
    id: str
    meeting_id: str
    speaker_id: str
    text: str
    timestamp: float
    is_final: bool
    confidence: float | None = None
    version: int = 1
