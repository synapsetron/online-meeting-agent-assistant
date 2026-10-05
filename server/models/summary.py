from __future__ import annotations

from typing import Literal

from .base import CamelModel


class SpeakerStats(CamelModel):
    speaker_id: str
    segments: int
    words: int
    share: float  # fraction of all transcribed words, 0..1


class AgendaItemStats(CamelModel):
    item_id: str | None  # None = speech while no agenda item was active
    title: str
    status: str
    elapsed_seconds: float
    estimated_minutes: float | None = None
    segments: int
    words: int
    share: float


class MeetingStats(CamelModel):
    duration_seconds: float
    final_segments: int
    total_words: int
    speakers: list[SpeakerStats]
    agenda: list[AgendaItemStats]
    hints_shown: int


class ActionItem(CamelModel):
    task: str
    owner: str | None = None


class MeetingReport(CamelModel):
    """Content summary of a meeting. ``source`` tells the UI whether the text
    came from the LLM or whether only the deterministic fallback is available
    (``note`` then carries the reason code)."""

    source: Literal["llm", "fallback"]
    summary: str = ""
    key_points: list[str] = []
    decisions: list[str] = []
    action_items: list[ActionItem] = []
    open_questions: list[str] = []
    truncated: bool = False
    note: str | None = None
