from __future__ import annotations

import re
from dataclasses import dataclass, field

from server.models import AgendaState, TranscriptSegment


TRANSITION_PHRASES_EN = [
    "let's move on to",
    "let's move to",
    "moving on to",
    "next topic",
    "next item",
    "next point",
    "let's discuss",
    "let's talk about",
    "now let's",
    "turning to",
    "shifting to",
    "let's switch to",
    "on to the next",
    "the next agenda",
    "moving forward",
]

TRANSITION_PHRASES_UK = [
    "перейдемо до",
    "перейдімо до",
    "переходимо до",
    "наступне питання",
    "наступний пункт",
    "давайте обговоримо",
    "тепер поговоримо",
    "далі",
    "наступна тема",
    "перейдемо далі",
    "переходимо далі",
]

_TRANSITION_PHRASES = TRANSITION_PHRASES_EN + TRANSITION_PHRASES_UK

_MIN_WORDS = 3


@dataclass
class TranscriptAnalysis:
    detected_topics: list[str] = field(default_factory=list)
    matched_agenda_item_ids: list[str] = field(default_factory=list)
    is_transition_signal: bool = False


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _word_in(word: str, normalized: str) -> bool:
    # Crude stemming for inflected (e.g. Ukrainian) forms: "погода" ~ "погоду".
    if word in normalized:
        return True
    return len(word) > 4 and word[:-2] in normalized


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


class TranscriptAnalyzer:
    def analyze(
        self,
        segment: TranscriptSegment,
        agenda: AgendaState,
    ) -> TranscriptAnalysis:
        text = segment.text.strip()
        words = _tokenize(text)

        if len(words) < _MIN_WORDS:
            return TranscriptAnalysis()

        normalized = _normalize(text)

        is_transition = any(
            phrase in normalized for phrase in _TRANSITION_PHRASES
        )

        detected_topics: list[str] = []
        matched_ids: list[str] = []

        for item in agenda.items:
            title_lower = item.title.lower()
            title_words = _tokenize(item.title)

            significant = [w for w in title_words if len(w) > 2]
            hits = sum(1 for w in significant if _word_in(w, normalized))
            title_matched = title_lower in normalized or (
                bool(significant) and hits >= (len(significant) + 1) // 2
            )

            desc_matched = False
            if item.description:
                desc_words = [
                    w for w in _tokenize(item.description) if len(w) > 3
                ]
                if desc_words:
                    overlap = sum(1 for w in desc_words if _word_in(w, normalized))
                    desc_matched = overlap >= max(1, len(desc_words) // 2)

            if title_matched or desc_matched:
                detected_topics.append(item.title)
                matched_ids.append(item.id)

        return TranscriptAnalysis(
            detected_topics=detected_topics,
            matched_agenda_item_ids=matched_ids,
            is_transition_signal=is_transition,
        )
