from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable

from server.config import Config
from server.core.logging_config import log_event
from server.models import (
    AgendaItemStatus,
    Hint,
    HintType,
    TranscriptSegment,
)
from server.agents.agenda_tracker import AgendaDelta, AgendaTracker
from server.agents.hint_generator import HintGenerator
from server.agents.summary_agent import SummaryAgent
from server.agents.transcript_analyzer import TranscriptAnalyzer

if TYPE_CHECKING:
    from server.core.state_store import MeetingStateStore

logger = logging.getLogger(__name__)

_OVERTIME_FACTOR = 1.5


HintSink = Callable[[list[Hint]], Awaitable[None]]


@dataclass
class OrchestratorResult:
    agenda_delta: AgendaDelta | None = None
    # LLM hints are produced in the background and delivered through the hint
    # sink (or ``Orchestrator.drain()``), so this list stays empty.
    hints: list[Hint] = field(default_factory=list)
    time_warnings: list[Hint] = field(default_factory=list)
    llm_triggered: bool = False


_SUMMARY_INTERVAL = 10_000  # default: effectively disabled
_HINT_REPEAT_COOLDOWN = 120.0  # seconds before the same hint type/item may repeat
_TIME_WARNING_COOLDOWN = 300.0  # an overtime item is re-announced at most this often
_FLUSH_RETRY_SECONDS = 0.25  # idle-flush re-check interval while a call is in flight


class Orchestrator:
    def __init__(self, config: Config, api_key_override: str | None = None) -> None:
        self._config = config
        self._analyzer = TranscriptAnalyzer()
        self._tracker = AgendaTracker()
        self._hint_gen = HintGenerator(
            api_key=api_key_override or config.anthropic_api_key,
            model=config.anthropic_model,
            timeout=config.llm_timeout_seconds,
            max_output_tokens=config.llm_max_output_tokens,
        )
        self._summary_agent = SummaryAgent(self._hint_gen, config)
        self._llm_calls = 0
        self._last_skip_reason: str | None = None
        self._recent_hint_keys: dict[tuple[str, str], float] = {}

        self._last_llm_call_time: float = 0.0
        self._pending_segments: list[TranscriptSegment] = []

        # Background LLM call (single-flight) and its delivery channel.
        self._llm_task: asyncio.Task[None] | None = None
        self._hint_sink: HintSink | None = None
        self._undelivered_hints: list[Hint] = []
        self._closed = False

        # Idle flush: one timer task per session, re-armed by moving the deadline.
        self._state: MeetingStateStore | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._flush_deadline: float | None = None

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
        self._state = state

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

        active_before = state.agenda.active_item_id
        state.apply_agenda_delta(delta)
        state.tag_segment(segment.id, state.agenda.active_item_id)
        log_event(
            logger, "segment_analyzed",
            level=logging.INFO if delta.status_changes else logging.DEBUG,
            segment_id=segment.id,
            words=len(segment.text.split()),
            matched_items=analysis.matched_agenda_item_ids,
            transition_phrase=analysis.is_transition_signal,
            active_before=active_before,
            active_after=state.agenda.active_item_id,
            status_changes={k: str(getattr(v, "value", v)) for k, v in delta.status_changes.items()},
            active_elapsed_s=delta.elapsed_updates.get(state.agenda.active_item_id or "", None),
        )

        time_warnings = self._drop_repeated_hints(
            self._check_time_warnings(state, segment), cooldown=_TIME_WARNING_COOLDOWN
        )

        self._pending_segments.append(segment)

        # The LLM call never blocks segment processing: when the gates allow it
        # the call runs as a background task and hints arrive through the sink.
        llm_triggered = False
        now = time.monotonic()
        pending_words = self._pending_words()
        skip_reason = self._llm_skip_reason(now, pending_words, self._config.llm_min_new_words)
        if skip_reason is None:
            self._start_llm_call(state, trigger="segment")
            llm_triggered = True
        else:
            self._log_llm_skip(skip_reason, pending_words, now)
            self._arm_idle_flush(now)

        # Trigger rolling summary update every _SUMMARY_INTERVAL final segments.
        segments_since = self._final_segment_count - self._last_summary_segment_count
        if segments_since >= self._config.summary_interval:
            self._maybe_start_summary_update(state)

        return OrchestratorResult(
            agenda_delta=delta,
            time_warnings=time_warnings,
            llm_triggered=llm_triggered,
        )

    # ------------------------------------------------------------------
    # Background LLM call: public contract
    # ------------------------------------------------------------------

    def set_hint_sink(self, callback: HintSink | None) -> None:
        """Register ``async def callback(hints: list[Hint]) -> None`` that receives
        hints produced by background LLM calls. Without a sink the hints are kept
        and returned by ``drain()``."""
        self._hint_sink = callback

    async def drain(self) -> list[Hint]:
        """Wait for the in-flight background LLM call (and run an idle flush that
        is already due), then return background hints not delivered to a sink.
        Safe to call repeatedly; never raises because of a failed LLM call."""
        while not self._closed:
            task = self._llm_task
            if task is not None and not task.done():
                # asyncio.wait does not cancel the call if drain() itself is cancelled.
                await asyncio.wait({task})
                continue
            if self._flush_is_due():
                self._run_idle_flush()
                if self._llm_in_flight():
                    continue
            break
        hints = self._undelivered_hints
        self._undelivered_hints = []
        return hints

    async def aclose(self) -> None:
        """Cancel the idle-flush timer and background tasks. Results that arrive
        after this point are dropped. Idempotent."""
        self._closed = True
        self._flush_deadline = None
        self._pending_segments.clear()
        tasks = [
            t for t in (self._flush_task, self._llm_task, self._summary_task)
            if t is not None and not t.done() and t is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # LLM gating
    # ------------------------------------------------------------------

    def _llm_in_flight(self) -> bool:
        return self._llm_task is not None and not self._llm_task.done()

    def _pending_words(self) -> int:
        return sum(len(s.text.split()) for s in self._pending_segments)

    def _min_interval_remaining(self, now: float) -> float:
        return self._config.llm_debounce_seconds - (now - self._last_llm_call_time)

    def _llm_skip_reason(self, now: float, pending_words: int, min_words: int) -> str | None:
        if self._llm_in_flight():
            return "call_in_flight"
        if self._llm_calls >= self._config.llm_max_calls_per_session:
            return "call_cap_reached"
        if self._hint_gen.usage.cost_usd >= self._config.llm_max_session_cost_usd:
            return "cost_cap_reached"
        if self._min_interval_remaining(now) > 0:
            return "min_interval"
        if pending_words < min_words:
            return "too_few_new_words"
        return None

    def _start_llm_call(self, state: MeetingStateStore, trigger: str) -> None:
        """Start the single-flight background hint call. The context is snapshotted
        here, so segments arriving during the call wait for the next one."""
        self._pending_segments.clear()
        self._flush_deadline = None
        self._llm_calls += 1
        self._last_llm_call_time = time.monotonic()
        self._llm_task = asyncio.create_task(
            self._run_llm_call(
                state,
                rolling_summary=state.get_rolling_summary(),
                recent=state.get_window(),
                trigger=trigger,
            )
        )

    async def _run_llm_call(
        self,
        state: MeetingStateStore,
        rolling_summary: str,
        recent: list[TranscriptSegment],
        trigger: str,
    ) -> None:
        try:
            hints = await self._hint_gen.generate(
                agenda=state.agenda,
                rolling_summary=rolling_summary,
                recent_segments=recent,
                recently_shown=self._recently_shown(),
            )
            if self._closed:
                # Stale result: the session ended while the model was answering.
                log_event(
                    logger, "llm_result_dropped", reason="session_closed",
                    trigger=trigger, hints=len(hints),
                )
                return
            fresh = self._drop_repeated_hints(hints)
            if not fresh:
                return
            if self._hint_sink is None:
                self._undelivered_hints.extend(fresh)
            else:
                await self._hint_sink(fresh)
        except asyncio.CancelledError:
            log_event(
                logger, "llm_result_dropped", level=logging.DEBUG,
                reason="cancelled", trigger=trigger,
            )
            raise
        except Exception:
            # A failed background call must never take the session down.
            logger.exception("llm_background_failed", extra={"trigger": trigger})

    # ------------------------------------------------------------------
    # Idle flush: analyse speech that was followed by a pause
    # ------------------------------------------------------------------

    def _arm_idle_flush(self, now: float) -> None:
        idle = self._config.llm_flush_idle_seconds
        if idle <= 0 or self._closed or not self._pending_segments:
            return
        self._flush_deadline = now + idle
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._idle_flush_loop())

    def _flush_is_due(self) -> bool:
        return (
            self._flush_deadline is not None
            and bool(self._pending_segments)
            and time.monotonic() >= self._flush_deadline
        )

    async def _idle_flush_loop(self) -> None:
        try:
            while not self._closed and self._flush_deadline is not None:
                delay = self._flush_deadline - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                    continue
                self._run_idle_flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("llm_flush_failed")

    def _run_idle_flush(self) -> None:
        """Deadline reached: start a call, re-arm for a temporary gate, or give up.
        Always moves or clears ``_flush_deadline``."""
        state = self._state
        if self._closed or state is None or not self._pending_segments:
            self._flush_deadline = None
            return

        now = time.monotonic()
        pending_words = self._pending_words()
        min_words = self._config.llm_flush_min_words
        if pending_words < min_words:
            reason: str | None = "too_few_new_words"
        else:
            reason = self._llm_skip_reason(now, pending_words, min_words)

        if reason is None:
            log_event(
                logger, "llm_flush",
                pending_words=pending_words, pending_segments=len(self._pending_segments),
                idle_seconds=self._config.llm_flush_idle_seconds,
                calls=self._llm_calls + 1,
            )
            self._start_llm_call(state, trigger="idle_flush")
            return

        self._log_llm_skip(reason, pending_words, now, trigger="idle_flush", min_words=min_words)
        if reason == "min_interval":
            self._flush_deadline = now + self._min_interval_remaining(now)
        elif reason == "call_in_flight":
            self._flush_deadline = now + max(
                self._min_interval_remaining(now), _FLUSH_RETRY_SECONDS
            )
        else:
            # Caps or too little speech: nothing to wait for until a new segment.
            self._flush_deadline = None

    def _log_llm_skip(
        self,
        reason: str,
        pending_words: int,
        now: float,
        trigger: str = "segment",
        min_words: int | None = None,
    ) -> None:
        hard_cap = reason in ("call_cap_reached", "cost_cap_reached")
        first_time = reason != self._last_skip_reason
        self._last_skip_reason = reason
        # Hard caps are logged once at WARNING; routine skips stay at DEBUG-level noise
        # unless the reason changed, so the log shows *why* hints are not coming.
        level = (
            logging.WARNING if hard_cap and first_time
            else logging.INFO if first_time
            else logging.DEBUG
        )
        log_event(
            logger, "llm_skipped", level=level, reason=reason, trigger=trigger,
            pending_words=pending_words,
            min_words=self._config.llm_min_new_words if min_words is None else min_words,
            seconds_since_last_call=round(now - self._last_llm_call_time, 1)
            if self._last_llm_call_time else None,
            calls=self._llm_calls, max_calls=self._config.llm_max_calls_per_session,
            session_cost_usd=round(self._hint_gen.usage.cost_usd, 6),
        )

    def _recently_shown(self) -> list[tuple[str, str]]:
        """Hint (type, item) pairs still inside the repeat cooldown, passed to the
        model so it does not spend output tokens on a hint we would suppress."""
        now = time.monotonic()
        return [
            key for key, shown_at in self._recent_hint_keys.items()
            if now - shown_at < _HINT_REPEAT_COOLDOWN
        ]

    def _drop_repeated_hints(
        self, hints: list[Hint], cooldown: float = _HINT_REPEAT_COOLDOWN
    ) -> list[Hint]:
        now = time.monotonic()
        fresh: list[Hint] = []
        for hint in hints:
            key = (hint.type.value, hint.agenda_item_id)
            last = self._recent_hint_keys.get(key)
            if last is not None and now - last < cooldown:
                log_event(
                    logger, "hint_suppressed_repeat",
                    level=logging.DEBUG if hint.type == HintType.TIME_WARNING else logging.INFO,
                    hint_type=hint.type.value, agenda_item_id=hint.agenda_item_id,
                    seconds_since_last=round(now - last, 1),
                )
                continue
            self._recent_hint_keys[key] = now
            fresh.append(hint)
        return fresh

    @property
    def usage(self):  # type: ignore[no-untyped-def]
        return self._hint_gen.usage

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
            log_event(
                logger, "rolling_summary_updated",
                summary_chars=len(updated), segments=len(segments),
            )
        except Exception:
            logger.exception("rolling_summary_failed")

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

    @property
    def summary_agent(self) -> SummaryAgent:
        return self._summary_agent

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
