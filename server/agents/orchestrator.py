from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from server.config import Config
from server.models import (
    AgendaItemStatus,
    Hint,
    HintType,
    TranscriptSegment,
)
from server.agents.agenda_tracker import AgendaDelta, AgendaTracker
from server.agents.hint_generator import HintGenerator
from server.agents.transcript_analyzer import TranscriptAnalyzer

if TYPE_CHECKING:
    from server.core.state_store import MeetingStateStore

logger = logging.getLogger(__name__)

_OVERTIME_FACTOR = 1.5


@dataclass
class OrchestratorResult:
    agenda_delta: AgendaDelta | None = None
    hints: list[Hint] = field(default_factory=list)
    time_warnings: list[Hint] = field(default_factory=list)


_SUMMARY_INTERVAL = 10  # generate a rolling summary every N final segments


class Orchestrator:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._analyzer = TranscriptAnalyzer()
        self._tracker = AgendaTracker()
        self._hint_gen = HintGenerator(
            api_key=config.anthropic_api_key,
            model=config.anthropic_model,
            timeout=config.llm_timeout_seconds,
        )

        self._llm_lock = asyncio.Lock()
        self._last_llm_call_time: float = 0.0
        self._pending_segments: list[TranscriptSegment] = []

        self._final_segment_count: int = 0
        self._last_summary_segment_count: int = 0
        self._summary_segments_buffer: list[TranscriptSegment] = []
        self._summary_task: asyncio.Task[None] | None = None

    async def process_segment(
        self,
        segment: TranscriptSegment,
        state: MeetingStateStore,
    ) -> OrchestratorResult:
        state.add_segment(segment)

        if not segment.is_final:
            return OrchestratorResult()

        self._final_segment_count += 1
        self._summary_segments_buffer.append(segment)

        analysis = self._analyzer.analyze(segment, state.agenda)

        delta = self._tracker.track(
            agenda=state.agenda,
            analysis=analysis,
            segment_id=segment.id,
            current_time=segment.timestamp,
        )

        state.apply_agenda_delta(delta)

        time_warnings = self._check_time_warnings(state, segment)

        self._pending_segments.append(segment)

        hints: list[Hint] = []
        now = time.monotonic()
        debounce_ok = (
            now - self._last_llm_call_time >= self._config.llm_debounce_seconds
        )

        if debounce_ok and self._pending_segments and not self._llm_lock.locked():
            self._pending_segments.clear()
            hints = await self._call_hint_generator(state)

        # Trigger rolling summary update every _SUMMARY_INTERVAL final segments.
        segments_since = self._final_segment_count - self._last_summary_segment_count
        if segments_since >= _SUMMARY_INTERVAL:
            self._maybe_start_summary_update(state)

        return OrchestratorResult(
            agenda_delta=delta,
            hints=hints,
            time_warnings=time_warnings,
        )

    async def _call_hint_generator(
        self,
        state: MeetingStateStore,
    ) -> list[Hint]:
        async with self._llm_lock:
            self._last_llm_call_time = time.monotonic()
            recent = state.get_window()
            return await self._hint_gen.generate(
                agenda=state.agenda,
                rolling_summary=state.get_rolling_summary(),
                recent_segments=recent,
            )

    def _maybe_start_summary_update(self, state: MeetingStateStore) -> None:
        """Kick off a background task to update the rolling summary, unless
        one is already running."""
        if self._summary_task is not None and not self._summary_task.done():
            return

        segments_to_summarize = list(self._summary_segments_buffer)
        self._summary_segments_buffer.clear()
        self._last_summary_segment_count = self._final_segment_count

        self._summary_task = asyncio.create_task(
            self._update_rolling_summary(state, segments_to_summarize)
        )

    async def _update_rolling_summary(
        self,
        state: MeetingStateStore,
        segments: list[TranscriptSegment],
    ) -> None:
        """Ask the LLM to produce an updated rolling summary and persist it."""
        try:
            current = state.get_rolling_summary()
            updated = await self._hint_gen.summarize_segments(current, segments)
            state.update_rolling_summary(updated)
            logger.info(
                "Rolling summary updated (%d chars from %d segments)",
                len(updated),
                len(segments),
            )
        except Exception:
            logger.exception("Failed to update rolling summary")

    @staticmethod
    def _check_time_warnings(
        state: MeetingStateStore,
        segment: TranscriptSegment,
    ) -> list[Hint]:
        warnings: list[Hint] = []
        for item in state.agenda.items:
            if item.status != AgendaItemStatus.ACTIVE:
                continue
            if item.estimated_minutes is None:
                continue
            limit_seconds = item.estimated_minutes * 60 * _OVERTIME_FACTOR
            if item.elapsed_seconds > limit_seconds:
                warnings.append(
                    Hint(
                        id=uuid.uuid4().hex,
                        type=HintType.TIME_WARNING,
                        agenda_item_id=item.id,
                        message=(
                            f"'{item.title}' has exceeded its estimated time "
                            f"({item.estimated_minutes:.0f} min). "
                            f"Elapsed: {item.elapsed_seconds / 60:.1f} min."
                        ),
                        evidence_segment_ids=[segment.id],
                        confidence=1.0,
                        timestamp=segment.timestamp,
                    )
                )
        return warnings

    async def generate_summary(self, state: MeetingStateStore) -> str:
        covered = [
            item.title
            for item in state.agenda.items
            if item.status == AgendaItemStatus.COVERED
        ]
        pending = [
            item.title
            for item in state.agenda.items
            if item.status in (AgendaItemStatus.PENDING, AgendaItemStatus.SKIPPED)
        ]
        deferred = [
            item.title
            for item in state.agenda.items
            if item.status == AgendaItemStatus.DEFERRED
        ]
        active = [
            item.title
            for item in state.agenda.items
            if item.status == AgendaItemStatus.ACTIVE
        ]

        lines = ["Meeting Summary", "=" * 40]

        if covered:
            lines.append("\nCovered items:")
            for t in covered:
                lines.append(f"  - {t}")

        if active:
            lines.append("\nStill active at end:")
            for t in active:
                lines.append(f"  - {t}")

        if deferred:
            lines.append("\nDeferred items:")
            for t in deferred:
                lines.append(f"  - {t}")

        if pending:
            lines.append("\nNot reached:")
            for t in pending:
                lines.append(f"  - {t}")

        total_segments = len(state.get_window())
        lines.append(f"\nTotal transcript segments: {total_segments}")
        lines.append(
            f"Total elapsed: {state.agenda.total_elapsed_seconds / 60:.1f} min"
        )

        return "\n".join(lines)
