from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from server.core.circuit_breaker import CircuitBreaker
from server.models import AgendaState, Hint, HintType, TranscriptSegment

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PROMPT = """\
You are a meeting summarizer. Given the current rolling summary of the meeting \
so far and a list of new transcript segments, produce an updated concise summary \
(200-300 words) of what has been discussed.

Rules:
- Merge new information into the existing summary rather than appending.
- Preserve key decisions, action items, and important points.
- Drop redundant or trivial details.
- Write in clear, factual prose.
- Return only the summary text, no JSON or other formatting.
"""

_SYSTEM_PROMPT = """\
You are a meeting agenda monitoring assistant. Your job is to analyze the \
current meeting conversation against the agenda and generate actionable hints \
for the meeting facilitator.

Rules:
- Only reference agenda_item_id values from the provided agenda.
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


def _build_user_content(
    agenda: AgendaState,
    rolling_summary: str,
    recent_segments: list[TranscriptSegment],
) -> str:
    agenda_lines = []
    for item in agenda.items:
        status = item.status.value
        elapsed = f"{item.elapsed_seconds:.0f}s"
        est = f"est {item.estimated_minutes}min" if item.estimated_minutes else "no estimate"
        agenda_lines.append(
            f"- [{status}] {item.id}: {item.title} ({elapsed} elapsed, {est})"
        )
    agenda_block = "\n".join(agenda_lines)

    segment_lines = []
    for seg in recent_segments:
        segment_lines.append(f"[{seg.id}] ({seg.speaker_id}): {seg.text}")
    transcript_block = "\n".join(segment_lines)

    return (
        f"Current agenda state:\n{agenda_block}\n\n"
        f"Active item: {agenda.active_item_id or 'none'}\n\n"
        f"Rolling summary:\n{rolling_summary}\n\n"
        f"Recent transcript:\n<transcript>\n{transcript_block}\n</transcript>\n\n"
        f"Generate hints as a JSON array."
    )


def _parse_hints(
    raw: str,
    valid_item_ids: set[str],
    valid_segment_ids: set[str],
) -> list[Hint]:
    try:
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []
        data = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse LLM hint response as JSON")
        return []

    hints: list[Hint] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue

        item_id = entry.get("agenda_item_id", "")
        if item_id not in valid_item_ids:
            continue

        evidence_ids = entry.get("evidence_segment_ids", [])
        if not isinstance(evidence_ids, list):
            continue
        evidence_ids = [eid for eid in evidence_ids if eid in valid_segment_ids]
        if not evidence_ids:
            continue

        try:
            hint_type = HintType(entry.get("type", ""))
        except ValueError:
            continue

        confidence = entry.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        message = entry.get("message", "")
        if not isinstance(message, str) or not message.strip():
            continue

        hints.append(
            Hint(
                id=uuid.uuid4().hex,
                type=hint_type,
                agenda_item_id=item_id,
                message=message.strip(),
                evidence_segment_ids=evidence_ids,
                confidence=confidence,
                uncertainty=entry.get("uncertainty"),
                timestamp=time.time(),
            )
        )

    return hints


class HintGenerator:
    def __init__(self, api_key: str, model: str, timeout: float = 10.0) -> None:
        self._model = model
        self._timeout = timeout
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60.0,
            name="hint-generator",
        )
        if anthropic is None:
            self._client: Any = None
        else:
            self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        agenda: AgendaState,
        rolling_summary: str,
        recent_segments: list[TranscriptSegment],
    ) -> list[Hint]:
        if self._client is None:
            logger.warning("anthropic package not installed; skipping hint generation")
            return []

        if not self._circuit_breaker.allow_request():
            logger.info("Circuit breaker open; skipping LLM hint generation")
            return []

        valid_item_ids = {item.id for item in agenda.items}
        valid_segment_ids = {seg.id for seg in recent_segments}

        user_content = _build_user_content(agenda, rolling_summary, recent_segments)

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                timeout=self._timeout,
            )
        except Exception:
            logger.exception("LLM hint generation failed")
            self._circuit_breaker.record_failure()
            return []

        self._circuit_breaker.record_success()

        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        return _parse_hints(raw_text, valid_item_ids, valid_segment_ids)

    async def summarize_segments(
        self,
        current_summary: str,
        new_segments: list[TranscriptSegment],
    ) -> str:
        """Generate an updated rolling summary by merging *new_segments* into
        the *current_summary*.  Returns the updated summary string.
        """
        if self._client is None:
            logger.warning(
                "anthropic package not installed; skipping summary generation"
            )
            return current_summary

        segment_lines = [
            f"[{seg.id}] ({seg.speaker_id}): {seg.text}" for seg in new_segments
        ]
        transcript_block = "\n".join(segment_lines)

        user_content = (
            f"Current rolling summary:\n{current_summary or '(none yet)'}\n\n"
            f"New transcript segments:\n<transcript>\n{transcript_block}\n</transcript>\n\n"
            f"Produce the updated summary."
        )

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                timeout=15.0,
            )
        except Exception:
            logger.exception("LLM summary generation failed")
            return current_summary

        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        return raw_text.strip() or current_summary
