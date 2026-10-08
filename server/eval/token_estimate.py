"""Offline token ESTIMATE (not a tokenizer) and its single calibration point.

There is no model tokenizer available offline, so token counts in the replay
harness are heuristic estimates. Do not report them as measurements.

Why a character-class heuristic and not ``len(text) / 4``:
- Ukrainian (Cyrillic) text splits into noticeably more tokens per character
  than English;
- UUID-like ids (``3f2a9c1e-...``) alternate short digit/letter runs and hyphens
  and are far more expensive per character than prose;
- punctuation and line breaks are usually tokens of their own.

Heuristic: split the text into maximal runs of one character class and charge
each run ``ceil(len / chars_per_token)`` (so every run costs at least one token);
spaces are free (they merge into the next token). All constants live below.

Calibration: ``CYRILLIC_CHARS_PER_TOKEN`` and ``LATIN_CHARS_PER_TOKEN`` were
picked on a coarse grid (step 0.5 / 1.0) so that a reconstruction of the one real
call we have numbers for lands within a few percent of its measured input size
(see ``CALIBRATION``). The other constants are plain assumptions and were NOT
fitted. One data point cannot validate the per-class split, and the original
transcript text of that call was (deliberately) never logged, so the
reconstruction uses synthetic text of the same size.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

# --- heuristic constants (single place) ------------------------------------
LATIN_CHARS_PER_TOKEN = 5.0  # per word-run; chosen together with the Cyrillic constant, see CALIBRATION
CYRILLIC_CHARS_PER_TOKEN = 2.0  # fitted to the calibration point, see CALIBRATION
DIGIT_CHARS_PER_TOKEN = 2.0  # digit runs split into short groups (assumption)
OTHER_LETTER_CHARS_PER_TOKEN = 1.0  # any other script: one token per character (assumption)
TOKENS_PER_PUNCTUATION_CHAR = 1.0  # each punctuation/symbol character (assumption)
TOKENS_PER_NEWLINE_RUN = 1.0  # a run of line breaks (assumption)
REQUEST_OVERHEAD_TOKENS = 8  # message framing per request (assumption)

_RUN_RE = re.compile(
    r"(?P<latin>[A-Za-z]+)"
    r"|(?P<cyrillic>[Ѐ-ԯ]+)"
    r"|(?P<digit>[0-9]+)"
    r"|(?P<newline>[\r\n]+)"
    r"|(?P<space>[ \t\f\v ]+)"
    r"|(?P<other>.)",
    re.DOTALL,
)


def estimate_text_tokens(text: str) -> int:
    """ESTIMATED number of tokens in ``text`` (heuristic, see module docstring).

    Monotonic: appending characters never lowers the estimate.
    """
    total = 0.0
    for match in _RUN_RE.finditer(text):
        kind = match.lastgroup
        length = len(match.group())
        if kind == "latin":
            total += math.ceil(length / LATIN_CHARS_PER_TOKEN)
        elif kind == "cyrillic":
            total += math.ceil(length / CYRILLIC_CHARS_PER_TOKEN)
        elif kind == "digit":
            total += math.ceil(length / DIGIT_CHARS_PER_TOKEN)
        elif kind == "newline":
            total += TOKENS_PER_NEWLINE_RUN
        elif kind == "space":
            continue
        elif match.group().isalpha():
            total += math.ceil(length / OTHER_LETTER_CHARS_PER_TOKEN)
        else:
            total += TOKENS_PER_PUNCTUATION_CHAR
    return math.ceil(total)


def _content_text(content: Any) -> str:
    """Text of a Messages API ``system``/``content`` value (string or text blocks)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text", ""))
    if isinstance(content, (list, tuple)):
        return "\n".join(_content_text(block) for block in content)
    return str(getattr(content, "text", ""))


def request_text_parts(request: dict[str, Any]) -> list[str]:
    """The billable text of a ``messages.create`` request: system + every message."""
    parts = [_content_text(request.get("system"))]
    for message in request.get("messages") or []:
        parts.append(_content_text(message.get("content") if isinstance(message, dict) else message))
    return [p for p in parts if p]


def estimate_request_input_tokens(request: dict[str, Any]) -> int:
    """ESTIMATED input tokens of one ``messages.create(**request)`` call."""
    return REQUEST_OVERHEAD_TOKENS + sum(estimate_text_tokens(p) for p in request_text_parts(request))


# ---------------------------------------------------------------------------
# Calibration point: the only real measurement available (session 4fb003db,
# 2026-10-08): 4 segments (52 Ukrainian words in total), 2 agenda items, the
# system prompt of that day -> 742 input / 215 output tokens (thinking disabled).
# ---------------------------------------------------------------------------

MEASURED_INPUT_TOKENS = 742
MEASURED_OUTPUT_TOKENS = 215

# Snapshot of the hint system prompt and user-content layout used on the day of
# the measurement (before the WP1 prompt rewrite). Kept only for calibration.
_LEGACY_SYSTEM_PROMPT = """\
You are a meeting agenda monitoring assistant. Your job is to analyze the \
current meeting conversation against the agenda and generate actionable hints \
for the meeting facilitator.

Rules:
- Only reference agenda_item_id values from the provided agenda. For topic_drift, \
use the active item's id (or the closest item) as the item being drifted away from.
- If the recent conversation is unrelated to the active agenda item, emit a \
topic_drift hint.
- Only reference evidence_segment_ids from the provided transcript segments.
- Set confidence between 0.0 and 1.0.
- Generate hints only when there is clear evidence in the transcript.
- Provide concise, actionable messages.
- Respond with a JSON array of hint objects. Each object has these fields:
  type (one of: agenda_suggestion, topic_drift, time_warning, missed_item, summary),
  agenda_item_id (string), message (string), evidence_segment_ids (list of strings),
  confidence (float 0-1), uncertainty (string or null).
- If there are no hints to generate, respond with an empty array: []
"""

# Synthetic stand-in for the unlogged transcript: 4 segments, 52 words in total.
_CALIBRATION_SEGMENTS = (
    ("0b7e6f52-3c1d-4a8e-9f27-5d1c0a94e6b3",
     "Почнімо зі статусу спринту: що ми встигли закрити за цей тиждень і що залишилося?"),
    ("c41a9d08-7e25-4f3b-8a16-2e9b7d5f0c84",
     "У цьому спринті ми закрили дванадцять задач із запланованих п'ятнадцяти, три ще в роботі."),
    ("9e3f1b6a-d2c4-4705-b8e9-6a1f4c3d7e20",
     "Задачу з авторизацією перенесли, оскільки змінилися вимоги від замовника, тому оцінку треба переглянути."),
    ("5a8d2c7f-1b94-4e60-a3d5-8f0e6b2c9a17",
     "Я закінчив інтеграцію з платіжним сервісом і передав її на рев'ю."),
)
_CALIBRATION_AGENDA = (
    ("active", "item-1791006808101-scy4", "Статус спринту", 31, 2.0),
    ("pending", "item-1791006812318-k9qd", "План релізу", 0, 3.0),
)


def _legacy_user_content() -> str:
    agenda_block = "\n".join(
        f"- [{status}] {item_id}: {title} ({elapsed}s elapsed, est {minutes}min)"
        for status, item_id, title, elapsed, minutes in _CALIBRATION_AGENDA
    )
    transcript_block = "\n".join(f"[{seg_id}] {text}" for seg_id, text in _CALIBRATION_SEGMENTS)
    return (
        f"Current agenda state:\n{agenda_block}\n\n"
        f"Active item: {_CALIBRATION_AGENDA[0][1]}\n\n"
        f"Recent transcript:\n<transcript>\n{transcript_block}\n</transcript>\n\n"
        "Generate hints as a JSON array."
    )


@dataclass(frozen=True)
class Calibration:
    measured_input_tokens: int
    estimated_input_tokens: int
    measured_output_tokens: int
    segments: int
    words: int
    agenda_items: int

    @property
    def relative_error(self) -> float:
        return self.estimated_input_tokens / self.measured_input_tokens - 1.0


def calibration_request() -> dict[str, Any]:
    """Reconstruction (synthetic text, real layout) of the measured request."""
    return {
        "system": _LEGACY_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _legacy_user_content()}],
    }


def calibration() -> Calibration:
    """Compare the heuristic with the one real measurement."""
    return Calibration(
        measured_input_tokens=MEASURED_INPUT_TOKENS,
        estimated_input_tokens=estimate_request_input_tokens(calibration_request()),
        measured_output_tokens=MEASURED_OUTPUT_TOKENS,
        segments=len(_CALIBRATION_SEGMENTS),
        words=sum(len(text.split()) for _, text in _CALIBRATION_SEGMENTS),
        agenda_items=len(_CALIBRATION_AGENDA),
    )


CALIBRATION = calibration()
