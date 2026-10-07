"""Offline, zero-cost replay harness comparing LLM-cost configurations (WP3).

Replays the synthetic scripted meetings from ``server.eval.scenarios`` through
the real ``Orchestrator`` with

* a FAKE Anthropic client (no network, no API key, no spend), and
* SIMULATED time (a 30-minute meeting replays in milliseconds),

and reports, per configuration profile: number of LLM calls, ESTIMATED input and
output tokens, ESTIMATED cost, and the simulated delay that call gating adds
between a segment arriving and the LLM call that first includes it.

Everything token- or money-related that this module prints is an estimate, not a
measurement: input tokens come from a character-class heuristic applied to the
actual request text (``server.eval.token_estimate``), output tokens are an
explicit per-profile assumption (low/high). Hint quality is not evaluated at all.

Usage::

    server/.venv/bin/python -m server.eval.cost_replay [--markdown PATH]

How time is simulated (isolated to this harness):

* the replay runs on its own event loop whose clock is a ``SimClock``; instead of
  blocking in ``select`` the loop jumps the clock to the next timer, so
  ``asyncio.sleep`` / ``call_later`` (e.g. the orchestrator's idle-flush timer)
  fire in simulated time;
* inside ``server.*`` modules the ``time`` module reference is swapped for a shim
  whose ``monotonic()`` / ``time()`` read the same clock. The global ``time``
  module is never patched and everything is restored when the replay ends.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as _dt
import hashlib
import json
import logging
import os
import re
import statistics
import subprocess
import sys
import time as _real_time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Literal, Sequence

from server.agents import hint_generator as _hint_generator_module
from server.agents.orchestrator import Orchestrator
from server.config import Config
from server.core.cost import PRICES_USD_PER_MTOK
from server.core.state_store import MeetingStateStore
from server.eval.scenarios import MEETING_EPOCH_MS, SCENARIOS, Scenario
from server.eval.token_estimate import (
    CALIBRATION,
    CYRILLIC_CHARS_PER_TOKEN,
    DIGIT_CHARS_PER_TOKEN,
    LATIN_CHARS_PER_TOKEN,
    MEASURED_OUTPUT_TOKENS,
    REQUEST_OVERHEAD_TOKENS,
    estimate_request_input_tokens,
    estimate_text_tokens,
    request_text_parts,
)
from server.models import AgendaItem, Hint, TranscriptSegment

Assumption = Literal["low", "high"]
ASSUMPTIONS: tuple[Assumption, ...] = ("low", "high")

# --- output-token assumptions (single place) --------------------------------
# Output tokens cannot be derived from a fake model, so each profile carries a
# low and a high ASSUMPTION per call. ``None`` means "the request's max_tokens"
# (the hard upper bound the API would enforce).
EMPTY_JSON_OUTPUT_TOKENS = 5  # assumption: the answer is just `[]`
NONEMPTY_JSON_OUTPUT_TOKENS = MEASURED_OUTPUT_TOKENS  # the one measured call (215, thinking off, old verbose schema)
NO_CAP = 10**9  # "effectively no cap" for the first-version profiles

_SIM_CLOCK_START = 1_000_000.0  # like a real monotonic clock, far from zero

# Canned rolling summary returned by the fake for summary requests (synthetic).
_CANNED_SUMMARY = (
    "Команда обговорила статус спринту: більшість задач закрито, кілька залишаються в роботі "
    "через зміну вимог і повільне рев'ю коду. Домовилися переглядати зміни до обіду та "
    "розподілити задачі без виконавця. Серед блокерів названо нестабільне тестове середовище, "
    "відсутній доступ до нової бази даних і брак макетів; питання доступу піднімуть на рівні "
    "керівника. Реліз заплановано на середу із заморожуванням коду в п'ятницю; сповіщення "
    "перенесено в наступну версію. Частину бюджету тестування пропонують спрямувати на "
    "автоматизацію регресійних тестів і закласти резерв на перевірку на реальних пристроях."
)
_CANNED_DRIFT_MESSAGE = "Розмова відійшла від активного пункту; запропонуйте повернутися до порядку денного."


# ---------------------------------------------------------------------------
# Configuration profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutputAssumption:
    """ASSUMED output tokens per call; ``None`` = up to the request's max_tokens."""

    hint_tokens: int | None
    summary_tokens: int | None


@dataclass(frozen=True)
class Profile:
    key: str
    label: str  # Ukrainian, for the results document
    config: Config
    thinking_assumed_on: bool
    output_low: OutputAssumption
    output_high: OutputAssumption

    def output(self, assumption: Assumption) -> OutputAssumption:
        return self.output_low if assumption == "low" else self.output_high


def build_profiles() -> list[Profile]:
    """K0..K4 of the ablation (docs/challenge-llm-cost-optimization.md, section 6).

    K0-K3 are built with explicit keyword arguments; every Config field not
    listed keeps the repository's current default (this includes the idle-flush
    settings). All profiles run through the CURRENT prompt format and request
    options: the harness cannot resurrect old prompt text, so K0-K3 differ only
    in the listed parameters and in the assumed output size.
    """
    summary_tokens = estimate_text_tokens(_CANNED_SUMMARY)
    # Thinking on (the API default when `thinking` is omitted): the answer is at
    # least as large as the measured thinking-off answer and at most max_tokens.
    thinking_low = OutputAssumption(NONEMPTY_JSON_OUTPUT_TOKENS, summary_tokens)
    thinking_high = OutputAssumption(None, None)
    # Thinking off: between an empty array and the one measured non-empty answer.
    plain_low = OutputAssumption(EMPTY_JSON_OUTPUT_TOKENS, summary_tokens)
    plain_high = OutputAssumption(NONEMPTY_JSON_OUTPUT_TOKENS, summary_tokens)

    k0 = Config(
        anthropic_api_key="offline",
        anthropic_model="claude-sonnet-5-5",
        transcript_window_size=20,
        llm_debounce_seconds=2.5,
        llm_min_new_words=0,
        llm_max_calls_per_session=NO_CAP,
        llm_max_session_cost_usd=float(NO_CAP),
        llm_max_output_tokens=1024,
        summary_interval=10,
    )
    k1 = Config(
        anthropic_api_key="offline",
        anthropic_model="claude-haiku-5-5",
        transcript_window_size=20,
        llm_debounce_seconds=2.5,
        llm_min_new_words=0,
        llm_max_calls_per_session=NO_CAP,
        llm_max_session_cost_usd=float(NO_CAP),
        llm_max_output_tokens=1024,
        summary_interval=10,
    )
    k2 = Config(
        anthropic_api_key="offline",
        anthropic_model="claude-haiku-5-5",
        transcript_window_size=20,
        llm_debounce_seconds=45.0,
        llm_min_new_words=50,
        llm_max_calls_per_session=NO_CAP,
        llm_max_session_cost_usd=float(NO_CAP),
        llm_max_output_tokens=1024,
        summary_interval=10,
    )
    k3 = Config(
        anthropic_api_key="offline",
        anthropic_model="claude-haiku-5-5",
        transcript_window_size=8,
        llm_debounce_seconds=45.0,
        llm_min_new_words=50,
        llm_max_calls_per_session=NO_CAP,
        llm_max_session_cost_usd=float(NO_CAP),
        llm_max_output_tokens=1024,
        summary_interval=NO_CAP,
    )
    k4 = Config(anthropic_api_key="offline")
    return [
        Profile("K0", "перша версія", k0, True, thinking_low, thinking_high),
        Profile("K1", "K0, змінено лише модель", k1, True, thinking_low, thinking_high),
        Profile("K2", "K1 + гейтинг викликів", k2, True, thinking_low, thinking_high),
        Profile("K3", "K2 + вікно 8, thinking вимкнено, без підсумку", k3, False, plain_low, plain_high),
        Profile("K4", "поточні типові значення репозиторію", k4, False, plain_low, plain_high),
    ]


# ---------------------------------------------------------------------------
# Simulated time
# ---------------------------------------------------------------------------


class SimClock:
    """Manually advanced clock shared by the event loop and the time shim."""

    def __init__(self, start: float = _SIM_CLOCK_START) -> None:
        self.start = start
        self.now = start

    @property
    def elapsed(self) -> float:
        return self.now - self.start

    def advance(self, seconds: float) -> None:
        if seconds > 0:
            self.now += seconds


class SimulatedTimeEventLoop(asyncio.SelectorEventLoop):
    """Event loop that never sleeps: waiting for a timer jumps the SimClock."""

    _MAX_IDLE_POLLS = 200  # x 10 ms of real time before declaring a deadlock

    def __init__(self, clock: SimClock) -> None:
        super().__init__()
        self._sim_clock = clock
        self._idle_polls = 0
        real_select = self._selector.select

        def select(timeout: float | None = None) -> Any:
            if timeout is None:
                # Nothing ready and no timer: only a real thread/IO could wake us.
                self._idle_polls += 1
                if self._idle_polls > self._MAX_IDLE_POLLS:
                    raise RuntimeError("simulated event loop is deadlocked (no timers, nothing ready)")
                return real_select(0.01)
            self._idle_polls = 0
            clock.advance(timeout)
            return real_select(0)

        self._selector.select = select  # type: ignore[method-assign]

    def time(self) -> float:
        return self._sim_clock.now


class _TimeShim:
    """Stand-in for the ``time`` module inside ``server.*`` modules."""

    def __init__(self, clock: SimClock) -> None:
        self._clock = clock

    def monotonic(self) -> float:
        return self._clock.now

    def perf_counter(self) -> float:
        return self._clock.now

    def time(self) -> float:
        return MEETING_EPOCH_MS / 1000.0 + self._clock.elapsed

    def __getattr__(self, name: str) -> Any:
        return getattr(_real_time, name)


_PATCHED_FUNCTIONS = ("monotonic", "perf_counter", "time")


@contextlib.contextmanager
def simulated_time(clock: SimClock) -> Iterator[None]:
    """Route ``time`` lookups of already-imported ``server.*`` modules (except this
    package and the tests) to ``clock``. Restores every attribute on exit."""
    shim = _TimeShim(clock)
    undo: list[tuple[Any, str, Any]] = []
    try:
        for name, module in list(sys.modules.items()):
            if module is None or not name.startswith("server."):
                continue
            if name.startswith(("server.eval", "server.tests")):
                continue
            namespace = getattr(module, "__dict__", {})
            if namespace.get("time") is _real_time:
                undo.append((module, "time", _real_time))
                setattr(module, "time", shim)
            for fn in _PATCHED_FUNCTIONS:  # `from time import monotonic` style
                original = namespace.get(fn)
                if original is not None and original is getattr(_real_time, fn):
                    undo.append((module, fn, original))
                    setattr(module, fn, getattr(shim, fn))
        yield
    finally:
        for module, attr, original in reversed(undo):
            setattr(module, attr, original)


@contextlib.contextmanager
def _quiet_server_logs() -> Iterator[None]:
    server_logger = logging.getLogger("server")
    previous = server_logger.level
    server_logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        server_logger.setLevel(previous)


# ---------------------------------------------------------------------------
# Fake LLM client
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMCallRecord:
    kind: str  # "hint" | "summary"
    sim_time_s: float  # simulated seconds from meeting start when the request was sent
    finals_seen: int  # final segments submitted to the orchestrator by then
    model: str
    max_tokens: int
    est_input_tokens: int
    est_output_tokens: int
    canned_hint: bool = False


class FakeAnthropicClient:
    """Drop-in for ``anthropic.AsyncAnthropic`` covering ``messages.create`` only.

    Records every request and answers instantly (or after ``latency_s`` simulated
    seconds) with a valid empty JSON array, a canned drift hint, or a canned
    summary. Usage numbers in the response are ESTIMATES (see module docstring).
    """

    def __init__(
        self,
        clock: SimClock,
        output: OutputAssumption,
        scenario: Scenario,
        latency_s: float = 0.0,
    ) -> None:
        self._clock = clock
        self._output = output
        self._scenario = scenario
        self._latency_s = latency_s
        self.finals_seen = 0  # updated by the replay loop
        self.requests: list[dict[str, Any]] = []
        self.calls: list[LLMCallRecord] = []
        self.messages = SimpleNamespace(create=self._create)

    @staticmethod
    def _kind(request: dict[str, Any]) -> str:
        system = "\n".join(request_text_parts({"system": request.get("system")}))
        summary_prompt = getattr(_hint_generator_module, "_SUMMARY_SYSTEM_PROMPT", None)
        if summary_prompt is not None and system == summary_prompt:
            return "summary"
        return "summary" if "summarizer" in system.lower() else "hint"

    def _canned_drift_reply(self, request: dict[str, Any]) -> str | None:
        """One topic_drift hint in the compact schema, using aliases found in the
        prompt. Returns None when the prompt layout is not recognised."""
        if not self._scenario.canned_drift_hints or self.finals_seen < 1:
            return None
        if not self._scenario.segments[self.finals_seen - 1].off_agenda:
            return None
        content = "\n".join(request_text_parts({"messages": request.get("messages")}))
        segment_aliases = re.findall(r"^(s\d+):", content, flags=re.MULTILINE)
        if not segment_aliases:
            return None
        active = re.search(r"^Active:\s*(a\d+)", content, flags=re.MULTILINE)
        hint = {
            "t": "topic_drift",
            "a": active.group(1) if active else "a1",
            "m": _CANNED_DRIFT_MESSAGE,
            "e": [segment_aliases[-1]],
            "c": 0.8,
        }
        return json.dumps([hint], ensure_ascii=False)

    async def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        kind = self._kind(request)
        max_tokens = int(request.get("max_tokens") or 0)
        canned = None
        if kind == "summary":
            text = _CANNED_SUMMARY
            assumed = self._output.summary_tokens
        else:
            canned = self._canned_drift_reply(request)
            text = canned or "[]"
            assumed = self._output.hint_tokens
        output_tokens = max_tokens if assumed is None else min(assumed, max_tokens or assumed)
        input_tokens = estimate_request_input_tokens(request)
        self.calls.append(
            LLMCallRecord(
                kind=kind,
                sim_time_s=self._clock.elapsed,
                finals_seen=self.finals_seen,
                model=str(request.get("model", "")),
                max_tokens=max_tokens,
                est_input_tokens=input_tokens,
                est_output_tokens=output_tokens,
                canned_hint=canned is not None,
            )
        )
        if self._latency_s > 0:
            await asyncio.sleep(self._latency_s)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    """One scenario x profile x output assumption. Token/cost fields are ESTIMATES."""

    scenario_key: str
    profile_key: str
    assumption: str
    model: str
    duration_s: float  # simulated
    final_segments: int
    words: int
    hint_calls: int
    summary_calls: int
    est_input_tokens: int
    est_output_tokens: int
    est_cost_usd: float
    # Gating delay: simulated seconds between a final segment arriving and the
    # hint call that first includes it. Excludes model latency by construction.
    gating_delay_median_s: float | None
    gating_delay_max_s: float | None
    segments_never_sent: int  # final segments that no hint call ever included
    hints_accepted: int  # hints that passed validation (canned hints only)
    time_warnings: int  # deterministic warnings, no LLM involved
    usage_meter_calls: int  # cross-check against Orchestrator.usage
    usage_meter_cost_usd: float
    request_options: dict[str, Any] = field(default_factory=dict, compare=False)
    hint_system_prompt_sha256: str = ""
    calls: tuple[LLMCallRecord, ...] = ()

    @property
    def llm_calls(self) -> int:
        return self.hint_calls + self.summary_calls

    @property
    def calls_per_minute(self) -> float:
        return self.llm_calls / (self.duration_s / 60.0)

    @property
    def est_cost_per_hour_usd(self) -> float:
        return self.est_cost_usd / (self.duration_s / 3600.0)


def price_for(model: str) -> tuple[float, float]:
    try:
        return PRICES_USD_PER_MTOK[model]
    except KeyError as exc:
        raise ValueError(
            f"no price for model {model!r} in server.core.cost.PRICES_USD_PER_MTOK; "
            "the replay cannot estimate cost for it"
        ) from exc


def gating_delays(
    scenario: Scenario, hint_calls: Sequence[LLMCallRecord], window: int
) -> tuple[list[float], int]:
    """Per-segment delay until the first hint call that includes the segment, and
    the number of segments no call included.

    A call sent after ``n`` final segments carries the last ``window`` of them
    (``MeetingStateStore.get_window``), so segment ``i`` (1-based) is included by
    the first call with ``finals_seen >= i`` provided ``finals_seen - i < window``.
    """
    delays: list[float] = []
    never = 0
    position = 0
    for index, segment in enumerate(scenario.segments, start=1):
        while position < len(hint_calls) and hint_calls[position].finals_seen < index:
            position += 1
        if position == len(hint_calls) or hint_calls[position].finals_seen - index >= window:
            never += 1
            continue
        delays.append(max(0.0, hint_calls[position].sim_time_s - segment.t_seconds))
    return delays, never


async def _drain(orchestrator: Any) -> list[Hint]:
    drain = getattr(orchestrator, "drain", None)
    if drain is None:
        return []
    return list(await drain() or [])


async def _await_summary(orchestrator: Any) -> None:
    task = getattr(orchestrator, "_summary_task", None)
    if isinstance(task, asyncio.Task) and not task.done():
        await asyncio.wait({task})


async def _replay(
    scenario: Scenario,
    profile: Profile,
    assumption: Assumption,
    clock: SimClock,
    llm_latency_s: float,
) -> RunResult:
    config = profile.config
    price_in, price_out = price_for(config.anthropic_model)

    orchestrator = Orchestrator(config)
    hint_gen = getattr(orchestrator, "_hint_gen", None)
    if hint_gen is None or not hasattr(hint_gen, "_client"):
        raise RuntimeError("Orchestrator._hint_gen._client seam not found; update the harness")
    fake = FakeAnthropicClient(clock, profile.output(assumption), scenario, llm_latency_s)
    hint_gen._client = fake

    state = MeetingStateStore(
        meeting_id=f"synthetic-{scenario.key}",
        agenda_items=[
            AgendaItem(id=a.id, title=a.title, estimated_minutes=a.estimated_minutes, order=i)
            for i, a in enumerate(scenario.agenda)
        ],
        window_size=config.transcript_window_size,
    )

    hints: list[Hint] = []
    time_warnings = 0
    try:
        for index, spec in enumerate(scenario.segments, start=1):
            wait = spec.t_seconds - clock.elapsed
            if wait > 0:
                await asyncio.sleep(wait)  # simulated; idle-flush timers fire in here
            fake.finals_seen = index
            result = await orchestrator.process_segment(
                TranscriptSegment(
                    id=spec.id,
                    meeting_id=state.meeting.id,
                    speaker_id=spec.speaker,
                    text=spec.text,
                    timestamp=MEETING_EPOCH_MS + spec.t_seconds * 1000.0,
                    is_final=True,
                ),
                state,
            )
            hints.extend(result.hints)
            time_warnings += len(result.time_warnings)
            hints.extend(await _drain(orchestrator))
            await _await_summary(orchestrator)

        remaining = scenario.duration_s - clock.elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)  # trailing silence: lets a due idle flush run
        hints.extend(await _drain(orchestrator))
        await _await_summary(orchestrator)
    finally:
        aclose = getattr(orchestrator, "aclose", None)
        if aclose is not None:
            await aclose()

    hint_calls = [c for c in fake.calls if c.kind == "hint"]
    delays, never = gating_delays(scenario, hint_calls, config.transcript_window_size)
    est_in = sum(c.est_input_tokens for c in fake.calls)
    est_out = sum(c.est_output_tokens for c in fake.calls)

    first_hint_request = next(
        (r for r, c in zip(fake.requests, fake.calls) if c.kind == "hint"), None
    )
    request_options: dict[str, Any] = {}
    prompt_hash = ""
    if first_hint_request is not None:
        request_options = {
            k: first_hint_request.get(k)
            for k in ("model", "max_tokens", "thinking", "output_config")
            if k in first_hint_request
        }
        system = "\n".join(request_text_parts({"system": first_hint_request.get("system")}))
        prompt_hash = hashlib.sha256(system.encode("utf-8")).hexdigest()

    usage = getattr(orchestrator, "usage", None)
    return RunResult(
        scenario_key=scenario.key,
        profile_key=profile.key,
        assumption=assumption,
        model=config.anthropic_model,
        duration_s=scenario.duration_s,
        final_segments=len(scenario.segments),
        words=scenario.total_words,
        hint_calls=len(hint_calls),
        summary_calls=len(fake.calls) - len(hint_calls),
        est_input_tokens=est_in,
        est_output_tokens=est_out,
        est_cost_usd=(est_in * price_in + est_out * price_out) / 1_000_000,
        gating_delay_median_s=statistics.median(delays) if delays else None,
        gating_delay_max_s=max(delays) if delays else None,
        segments_never_sent=never,
        hints_accepted=len(hints),
        time_warnings=time_warnings,
        usage_meter_calls=int(getattr(usage, "calls", 0) or 0),
        usage_meter_cost_usd=float(getattr(usage, "cost_usd", 0.0) or 0.0),
        request_options=request_options,
        hint_system_prompt_sha256=prompt_hash,
        calls=tuple(fake.calls),
    )


def run_replay(
    scenario: Scenario,
    profile: Profile,
    assumption: Assumption = "low",
    *,
    llm_latency_s: float = 0.0,
) -> RunResult:
    """Replay one scenario under one profile. Synchronous: owns a private event
    loop with simulated time, so do not call it from a running event loop."""
    clock = SimClock()
    with _quiet_server_logs(), simulated_time(clock):
        with asyncio.Runner(loop_factory=lambda: SimulatedTimeEventLoop(clock)) as runner:
            return runner.run(_replay(scenario, profile, assumption, clock, llm_latency_s))


