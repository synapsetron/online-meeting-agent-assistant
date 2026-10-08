from __future__ import annotations

import pytest

from server.models import AgendaItem, AgendaState, TranscriptSegment
from server.agents.transcript_analyzer import TranscriptAnalyzer


def _seg(seg_id: str, text: str) -> TranscriptSegment:
    return TranscriptSegment(
        id=seg_id,
        meeting_id="m-1",
        speaker_id="s-1",
        text=text,
        timestamp=0.0,
        is_final=True,
    )


def _agenda() -> AgendaState:
    return AgendaState(
        items=[
            AgendaItem(id="ag-1", title="Project overview", order=1),
            AgendaItem(id="ag-2", title="Architecture review", order=2),
            AgendaItem(id="ag-3", title="Timeline planning", order=3),
        ]
    )


class TestKeywordMatch:
    def test_segment_mentions_agenda_title(self) -> None:
        analyzer = TranscriptAnalyzer()
        seg = _seg("seg-1", "Let's discuss the project overview now")
        result = analyzer.analyze(seg, _agenda())
        assert "ag-1" in result.matched_agenda_item_ids

    def test_no_match_for_unrelated(self) -> None:
        analyzer = TranscriptAnalyzer()
        seg = _seg("seg-1", "The weather is nice today")
        result = analyzer.analyze(seg, _agenda())
        assert len(result.matched_agenda_item_ids) == 0


class TestTransitionPhrases:
    def test_english_transition(self) -> None:
        analyzer = TranscriptAnalyzer()
        seg = _seg("seg-1", "Let's move on to the architecture review")
        result = analyzer.analyze(seg, _agenda())
        assert result.is_transition_signal is True
        assert "ag-2" in result.matched_agenda_item_ids

    def test_ukrainian_transition(self) -> None:
        analyzer = TranscriptAnalyzer()
        seg = _seg("seg-1", "Перейдемо до timeline planning")
        result = analyzer.analyze(seg, _agenda())
        assert result.is_transition_signal is True


class TestShortSegments:
    def test_short_segment_returns_empty(self) -> None:
        analyzer = TranscriptAnalyzer()
        seg = _seg("seg-1", "ok yes")
        result = analyzer.analyze(seg, _agenda())
        assert len(result.matched_agenda_item_ids) == 0

    def test_single_word(self) -> None:
        analyzer = TranscriptAnalyzer()
        seg = _seg("seg-1", "hello")
        result = analyzer.analyze(seg, _agenda())
        assert len(result.matched_agenda_item_ids) == 0


def test_inflected_ukrainian_title_matches() -> None:
    from server.agents.transcript_analyzer import TranscriptAnalyzer
    from server.models import AgendaItem, AgendaState, TranscriptSegment

    agenda = AgendaState(items=[AgendaItem(id="w", title="Погода", order=1)])
    seg = TranscriptSegment(
        id="s", meeting_id="m", speaker_id="u", text="сьогодні гарну погоду обіцяли",
        timestamp=1.0, is_final=True,
    )
    assert "w" in TranscriptAnalyzer().analyze(seg, agenda).matched_agenda_item_ids
