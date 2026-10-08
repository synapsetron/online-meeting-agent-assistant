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


# ---------------------------------------------------------------------------
# Result matrix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    """One scenario x profile with the low and the high output assumption."""

    scenario_key: str
    profile_key: str
    low: RunResult
    high: RunResult
    cost_ratio_vs_k0_low: float | None = None
    cost_ratio_vs_k0_high: float | None = None


@dataclass(frozen=True)
class Aggregate:
    """All scenarios summed for one profile. Token/cost fields are ESTIMATES."""

    profile_key: str
    duration_s: float
    final_segments: int
    llm_calls: tuple[int, int]  # (low, high)
    summary_calls: tuple[int, int]
    est_input_tokens: tuple[int, int]
    est_output_tokens: tuple[int, int]
    est_cost_usd: tuple[float, float]
    gating_delay_median_s: float | None  # median over scenario medians (low run)
    gating_delay_max_s: float | None
    segments_never_sent: int
    cost_ratio_vs_k0: tuple[float | None, float | None] = (None, None)

    @property
    def calls_per_minute(self) -> tuple[float, float]:
        minutes = self.duration_s / 60.0
        return (self.llm_calls[0] / minutes, self.llm_calls[1] / minutes)

    @property
    def est_cost_per_hour_usd(self) -> tuple[float, float]:
        hours = self.duration_s / 3600.0
        return (self.est_cost_usd[0] / hours, self.est_cost_usd[1] / hours)


@dataclass(frozen=True)
class ReplayReport:
    profiles: tuple[Profile, ...]
    scenarios: tuple[Scenario, ...]
    cells: tuple[Cell, ...]
    aggregates: tuple[Aggregate, ...]

    def cell(self, scenario_key: str, profile_key: str) -> Cell:
        for cell in self.cells:
            if cell.scenario_key == scenario_key and cell.profile_key == profile_key:
                return cell
        raise KeyError((scenario_key, profile_key))

    def aggregate(self, profile_key: str) -> Aggregate:
        for aggregate in self.aggregates:
            if aggregate.profile_key == profile_key:
                return aggregate
        raise KeyError(profile_key)


def _ratio(value: float, base: float | None) -> float | None:
    return value / base if base else None


def run_matrix(
    scenarios: Sequence[Scenario] = SCENARIOS,
    profiles: Sequence[Profile] | None = None,
    baseline_key: str = "K0",
) -> ReplayReport:
    """Replay every scenario under every profile with both output assumptions."""
    profiles = list(profiles) if profiles is not None else build_profiles()
    runs: dict[tuple[str, str], tuple[RunResult, RunResult]] = {}
    for scenario in scenarios:
        for profile in profiles:
            runs[(scenario.key, profile.key)] = (
                run_replay(scenario, profile, "low"),
                run_replay(scenario, profile, "high"),
            )

    cells: list[Cell] = []
    for scenario in scenarios:
        base = runs.get((scenario.key, baseline_key))
        for profile in profiles:
            low, high = runs[(scenario.key, profile.key)]
            cells.append(
                Cell(
                    scenario.key, profile.key, low, high,
                    _ratio(low.est_cost_usd, base[0].est_cost_usd if base else None),
                    _ratio(high.est_cost_usd, base[1].est_cost_usd if base else None),
                )
            )

    aggregates: list[Aggregate] = []
    for profile in profiles:
        lows = [runs[(s.key, profile.key)][0] for s in scenarios]
        highs = [runs[(s.key, profile.key)][1] for s in scenarios]
        medians = [r.gating_delay_median_s for r in lows if r.gating_delay_median_s is not None]
        maxima = [r.gating_delay_max_s for r in lows if r.gating_delay_max_s is not None]
        aggregates.append(
            Aggregate(
                profile_key=profile.key,
                duration_s=sum(r.duration_s for r in lows),
                final_segments=sum(r.final_segments for r in lows),
                llm_calls=(sum(r.llm_calls for r in lows), sum(r.llm_calls for r in highs)),
                summary_calls=(sum(r.summary_calls for r in lows), sum(r.summary_calls for r in highs)),
                est_input_tokens=(sum(r.est_input_tokens for r in lows), sum(r.est_input_tokens for r in highs)),
                est_output_tokens=(sum(r.est_output_tokens for r in lows), sum(r.est_output_tokens for r in highs)),
                est_cost_usd=(sum(r.est_cost_usd for r in lows), sum(r.est_cost_usd for r in highs)),
                gating_delay_median_s=statistics.median(medians) if medians else None,
                gating_delay_max_s=max(maxima) if maxima else None,
                segments_never_sent=sum(r.segments_never_sent for r in lows),
            )
        )
    base_agg = next((a for a in aggregates if a.profile_key == baseline_key), None)
    if base_agg is not None:
        aggregates = [
            Aggregate(
                **{
                    **a.__dict__,
                    "cost_ratio_vs_k0": (
                        _ratio(a.est_cost_usd[0], base_agg.est_cost_usd[0]),
                        _ratio(a.est_cost_usd[1], base_agg.est_cost_usd[1]),
                    ),
                }
            )
            for a in aggregates
        ]
    return ReplayReport(tuple(profiles), tuple(scenarios), tuple(cells), tuple(aggregates))


# ---------------------------------------------------------------------------
# Rendering (Ukrainian: thesis material)
# ---------------------------------------------------------------------------


def _rng(low: Any, high: Any, fmt: str) -> str:
    a, b = format(low, fmt), format(high, fmt)
    return a if a == b else f"{a} – {b}"


def _opt(value: float | None, fmt: str = ".0f") -> str:
    return "—" if value is None else format(value, fmt)


def _pct(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "—"
    return _rng(low * 100, high * 100, ".2f") + " %"


_TABLE_HEADER = (
    "| Конфіг. | Трив., хв (симул.) | Фін. реплік | Викликів LLM (з них підсумок) | Викл./хв "
    "| Вх. токени (оцінка) | Вих. токени (оцінка, низ – верх) | Вартість, $ (оцінка, низ – верх) "
    "| $/год зустрічі (оцінка) | Відносно K0 (оцінка) | Затримка гейтингу, с: медіана / макс "
    "| Реплік поза викликами |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|"
)


def _row(
    key: str, duration_s: float, finals: int,
    calls: tuple[int, int], summary: tuple[int, int],
    tokens_in: tuple[int, int], tokens_out: tuple[int, int], cost: tuple[float, float],
    ratio: tuple[float | None, float | None],
    delay_median: float | None, delay_max: float | None, never: int,
) -> str:
    minutes = duration_s / 60.0
    hours = duration_s / 3600.0
    return (
        f"| {key} | {minutes:.1f} | {finals} "
        f"| {_rng(calls[0], calls[1], 'd')} ({_rng(summary[0], summary[1], 'd')}) "
        f"| {_rng(calls[0] / minutes, calls[1] / minutes, '.2f')} "
        f"| {_rng(tokens_in[0], tokens_in[1], 'd')} "
        f"| {_rng(tokens_out[0], tokens_out[1], 'd')} "
        f"| {_rng(cost[0], cost[1], '.5f')} "
        f"| {_rng(cost[0] / hours, cost[1] / hours, '.4f')} "
        f"| {_pct(*ratio)} "
        f"| {_opt(delay_median)} / {_opt(delay_max)} "
        f"| {never} |"
    )


def render_scenario_table(report: ReplayReport, scenario: Scenario) -> str:
    lines = [_TABLE_HEADER]
    for profile in report.profiles:
        cell = report.cell(scenario.key, profile.key)
        low, high = cell.low, cell.high
        lines.append(
            _row(
                profile.key, low.duration_s, low.final_segments,
                (low.llm_calls, high.llm_calls), (low.summary_calls, high.summary_calls),
                (low.est_input_tokens, high.est_input_tokens),
                (low.est_output_tokens, high.est_output_tokens),
                (low.est_cost_usd, high.est_cost_usd),
                (cell.cost_ratio_vs_k0_low, cell.cost_ratio_vs_k0_high),
                low.gating_delay_median_s, low.gating_delay_max_s, low.segments_never_sent,
            )
        )
    return "\n".join(lines)


def render_aggregate_table(report: ReplayReport) -> str:
    lines = [_TABLE_HEADER]
    for a in report.aggregates:
        lines.append(
            _row(
                a.profile_key, a.duration_s, a.final_segments, a.llm_calls, a.summary_calls,
                a.est_input_tokens, a.est_output_tokens, a.est_cost_usd, a.cost_ratio_vs_k0,
                a.gating_delay_median_s, a.gating_delay_max_s, a.segments_never_sent,
            )
        )
    return "\n".join(lines)


def render_tables(report: ReplayReport) -> str:
    """All tables (aggregate first). Every token and cost figure is an estimate."""
    parts = [
        "### Зведена таблиця (усі сценарії разом; усі токени й вартість — оцінка)",
        "",
        render_aggregate_table(report),
    ]
    for scenario in report.scenarios:
        parts += [
            "",
            f"### Сценарій `{scenario.key}` — {scenario.title} (синтетичний; оцінка)",
            "",
            f"{scenario.description} Реплік: {len(scenario.segments)}, слів: {scenario.total_words}, "
            f"у середньому {scenario.total_words / len(scenario.segments):.1f} слова на репліку.",
            "",
            render_scenario_table(report, scenario),
        ]
    return "\n".join(parts)


def _cap(value: float) -> str:
    return "без ліміту" if value >= NO_CAP else f"{value:g}"


def _out(value: int | None, max_tokens: int) -> str:
    return f"{max_tokens} (= max_tokens)" if value is None else str(min(value, max_tokens))


def render_profiles_table(report: ReplayReport) -> str:
    lines = [
        "| Конфіг. | Зміст | Модель | Ціна вх./вих., $ за 1 млн | Вікно | Мін. інтервал, с | Поріг слів "
        "| Ліміт викликів | Ліміт вартості, $ | max_tokens | Інтервал підсумку, реплік "
        "| Припущення: вих. токенів на виклик підказки (низ / верх) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for p in report.profiles:
        c = p.config
        price_in, price_out = price_for(c.anthropic_model)
        summary = "вимкнено" if c.summary_interval >= 10_000 else str(c.summary_interval)
        lines.append(
            f"| {p.key} | {p.label} | `{c.anthropic_model}` | {price_in:g} / {price_out:g} "
            f"| {c.transcript_window_size} | {c.llm_debounce_seconds:g} | {c.llm_min_new_words} "
            f"| {_cap(c.llm_max_calls_per_session)} | {_cap(c.llm_max_session_cost_usd)} "
            f"| {c.llm_max_output_tokens} | {summary} "
            f"| {_out(p.output_low.hint_tokens, c.llm_max_output_tokens)} / "
            f"{_out(p.output_high.hint_tokens, c.llm_max_output_tokens)} |"
        )
    return "\n".join(lines)


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=False,
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},  # read-only: never touch the index
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _file_sha(relative: str) -> str:
    path = Path(__file__).resolve().parents[2] / relative
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:
        return "недоступно"


def provenance(report: ReplayReport, command: str) -> dict[str, str]:
    tracked = ("server/agents/hint_generator.py", "server/agents/orchestrator.py", "server/config.py")
    dirty = [line for line in _git("status", "--porcelain", "--", "server").splitlines() if line.strip()]
    sample = next((c.low for c in report.cells if c.low.hint_system_prompt_sha256), None)
    k4 = next((c.low for c in report.cells if c.profile_key == "K4" and c.low.request_options), None)
    return {
        "date": _dt.date.today().isoformat(),
        "command": command,
        "git_head": _git("rev-parse", "--short", "HEAD") or "невідомо",
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "невідомо",
        "git_dirty_files": str(len(dirty)),
        "prompt_sha": sample.hint_system_prompt_sha256[:12] if sample else "немає викликів",
        "file_shas": ", ".join(f"`{name}` {_file_sha(name)}" for name in tracked),
        "request_options": json.dumps(k4.request_options, ensure_ascii=False) if k4 else "немає викликів",
        "python": sys.version.split()[0],
    }


def _per_call(cost: float, calls: int) -> str:
    return "—" if not calls else f"{cost / calls:.5f}"


def render_observations(report: ReplayReport) -> str:
    """Statements computed from the run (no interpretation beyond the numbers)."""
    by_key = {a.profile_key: a for a in report.aggregates}
    lines: list[str] = []
    k0, k1, k2, k3, k4 = (by_key.get(k) for k in ("K0", "K1", "K2", "K3", "K4"))
    if k0:
        cpm = k0.calls_per_minute
        hint_calls = (k0.llm_calls[0] - k0.summary_calls[0], k0.llm_calls[1] - k0.summary_calls[1])
        lines.append(
            f"- K0: оцінка стенда — {_rng(cpm[0], cpm[1], '.2f')} виклику/хв "
            f"(разом із викликами підсумку; лише підказки — "
            f"{hint_calls[0] / (k0.duration_s / 60):.2f}/хв) і "
            f"${_per_call(k0.est_cost_usd[0], k0.llm_calls[0])} – "
            f"${_per_call(k0.est_cost_usd[1], k0.llm_calls[1])} за виклик. Реконструкція в розд. 3 "
            "документа «Виклик 8» називає ~7.5 виклику/хв і ~$0.004 – $0.014 за виклик; "
            "стенд працює з поточним (стислішим) форматом промпта, тому вхідні токени K0 тут "
            "нижчі, ніж були б зі старим промптом."
        )
        usd = 0.90
        lines.append(
            f"- За оцінкою $/год для K0 ({_rng(*k0.est_cost_per_hour_usd, '.2f')}) сума $0.90 "
            f"відповідала б приблизно {usd / k0.est_cost_per_hour_usd[1] * 60:.0f} – "
            f"{usd / k0.est_cost_per_hour_usd[0] * 60:.0f} хв зустрічей. Це оцінка, а не "
            "розклад фактичного рахунку."
        )
    if k0 and k1:
        lines.append(
            f"- K0 → K1 (лише модель): вартість {_pct(*k1.cost_ratio_vs_k0)} від K0 — це прямий "
            "наслідок співвідношення цін у `PRICES_USD_PER_MTOK`, а не результат стенда; "
            "кількість викликів і токенів однакова за побудовою."
        )
    if k1 and k2:
        lines.append(
            f"- K1 → K2 (гейтинг): викликів {_rng(*k1.llm_calls, 'd')} → {_rng(*k2.llm_calls, 'd')} "
            f"(у {k1.llm_calls[0] / k2.llm_calls[0]:.1f} раза менше), ціною затримки гейтингу: "
            f"медіана {_opt(k2.gating_delay_median_s)} с, максимум {_opt(k2.gating_delay_max_s)} с "
            f"(у K1 — {_opt(k1.gating_delay_median_s)} / {_opt(k1.gating_delay_max_s)} с)."
            if k2.llm_calls[0] else "- K2 не зробив жодного виклику."
        )
    if k2 and k3:
        lines.append(
            f"- K2 → K3 (вікно 8, thinking вимкнено, без підсумку): вхідні токени "
            f"{_rng(*k2.est_input_tokens, 'd')} → {_rng(*k3.est_input_tokens, 'd')}; вихідні — "
            f"{_rng(*k2.est_output_tokens, 'd')} → {_rng(*k3.est_output_tokens, 'd')} (вихідні — "
            "це різниця ПРИПУЩЕНЬ, а не результат моделювання). Реплік, що не потрапили в жоден "
            f"виклик: {k2.segments_never_sent} → {k3.segments_never_sent}."
        )
    if k3 and k4:
        lines.append(
            f"- K3 → K4 (поточний код): викликів {_rng(*k3.llm_calls, 'd')} → {_rng(*k4.llm_calls, 'd')}; "
            f"оцінка $/год зустрічі {_rng(*k4.est_cost_per_hour_usd, '.4f')}. Оскільки K0–K3 теж "
            "проходять через поточний промпт, ефект WP1 (стислий промпт) у різниці K3 → K4 НЕ видно."
        )
    if k4:
        lines.append(
            f"- K4: реплік поза будь-яким викликом — {k4.segments_never_sent} із {k4.final_segments}; "
            f"затримка гейтингу — медіана {_opt(k4.gating_delay_median_s)} с, максимум "
            f"{_opt(k4.gating_delay_max_s)} с (без часу відповіді моделі)."
        )
    return "\n".join(lines)


def render_markdown(report: ReplayReport, command: str) -> str:
    """The complete results document (Ukrainian). Generated, do not edit by hand."""
    meta = provenance(report, command)
    cal = CALIBRATION
    canned = [
        (c.scenario_key, c.profile_key, sum(1 for call in c.low.calls if call.canned_hint), c.low.hints_accepted)
        for c in report.cells
        if any(call.canned_hint for call in c.low.calls)
    ]
    canned_text = (
        "; ".join(f"`{s}`/{p}: {n} відповідей із підказкою, прийнято {h}" for s, p, n, h in canned)
        if canned else "жодної"
    )
    return f"""\
# Офлайн-відтворення сценаріїв: оцінка вартості LLM за конфігураціями (WP3)

> Файл згенеровано скриптом `server/eval/cost_replay.py`; не редагуйте вручну — перегенеруйте.
> **Усі кількості токенів і всі суми в цьому документі — оцінка (не вимір).** Жодного звернення
> до API не було; відповіді моделі — заглушка. Якість підказок не оцінювалась.

Статус достовірності: кількість викликів і затримка гейтингу — результат детермінованого
відтворення реального коду оркестратора на синтетичних сценаріях у симульованому часі;
вхідні токени — евристична оцінка; вихідні токени — припущення; вартість — добуток цих
оцінок на ціни з `server/core/cost.py`.

## 1. Як отримано

- Дата прогону: {meta["date"]}.
- Команда: `{meta["command"]}`
- Стан коду: гілка `{meta["git_branch"]}`, коміт `{meta["git_head"]}`, незакомічених змін у `server/`: {meta["git_dirty_files"]} файл(ів).
  SHA-256 (перші 12 символів) файлів на момент прогону: {meta["file_shas"]}.
- Версія промпта: SHA-256 системного промпта підказок `{meta["prompt_sha"]}` (поточний формат із
  псевдонімами `a1`/`s1`). Параметри запиту K4, які бачила заглушка: `{meta["request_options"]}`.
- Python {meta["python"]}; зовнішніх залежностей понад наявні в `server/.venv` немає.

## 2. Метод

1. Синтетичні сценарії (`server/eval/scenarios.py`, українською, вигадані репліки, без реальних
   людей і записів): фінальна репліка кожні 6–10 симульованих секунд, 5–25 слів у репліці; довгі
   ідентифікатори, як у продукті (UUID реплік, `item-<мс>-<суфікс>` для пунктів).
2. Кожен сценарій проходить через справжній `Orchestrator` (аналізатор, трекер, гейтинг, фоновий
   виклик, відкладений «дозлив» після паузи). Час симульовано: цикл подій стенда не чекає, а
   пересуває годинник до наступного таймера; `time.monotonic()` у модулях `server.*` читає той
   самий годинник. Після останньої репліки моделюється {report.scenarios[0].trailing_silence_s:g} с тиші.
3. Клієнт Anthropic замінено заглушкою: вона записує запит, оцінює вхідні токени за фактичним
   текстом запиту (`system` + усі повідомлення) і повертає порожній масив `[]` (або заготовлену
   підказку `topic_drift` у сценарії з відхиленням, щоб пройти шлях обробки підказок; у цьому
   прогоні: {canned_text}).
4. Вихідні токени — припущення, по два на конфігурацію (низ / верх), тож кожен сценарій
   відтворюється двічі. Якщо thinking вважається увімкненим (K0–K2): низ = {NONEMPTY_JSON_OUTPUT_TOKENS}
   (розмір єдиної виміряної відповіді без thinking), верх = `max_tokens`. Якщо вимкненим (K3, K4):
   низ = {EMPTY_JSON_OUTPUT_TOKENS} (лише `[]`), верх = {NONEMPTY_JSON_OUTPUT_TOKENS}. Для викликів підсумку: оцінка
   розміру заготовленого підсумку, а у «верхньому» варіанті з thinking — `max_tokens` запиту.
5. Вартість = оцінка токенів × ціни з `server.core.cost.PRICES_USD_PER_MTOK`.
6. «Затримка гейтингу» — симульований час від надходження репліки до найближчого виклику
   підказок, у вікно якого вона потрапила. Це лише затримка через гейтинг: час відповіді
   моделі, мережа й розпізнавання мовлення до неї не входять. «Реплік поза викликами» — фінальні
   репліки, які не потрапили в жоден виклик (вийшли з вікна або після останнього виклику).

## 3. Конфігурації

{render_profiles_table(report)}

K0–K3 задано явно; решта полів `Config` (зокрема «дозлив» після паузи) — поточні типові
значення. K4 = `Config(anthropic_api_key="offline")`, тобто відстежує код репозиторію. Стенд не
може відтворити старий текст промпта: **K0–K3 використовують поточний формат промпта й
поточні параметри запиту і відрізняються лише переліченими параметрами та припущенням про
вихідні токени**. Тому оцінки вхідних токенів для K0–K2 занижені відносно справжньої першої
версії, а різниця K3 → K4 не показує ефекту стислого промпта (WP1).

## 4. Калібрування оцінки токенів

Токенізатора моделі офлайн немає. Функція `estimate_text_tokens` ділить текст на серії символів
одного класу й бере `ceil(довжина / k)` токенів на серію: латиниця k = {LATIN_CHARS_PER_TOKEN:g}, кирилиця
k = {CYRILLIC_CHARS_PER_TOKEN:g}, цифри k = {DIGIT_CHARS_PER_TOKEN:g}; кожен розділовий знак і кожна серія переносів рядка — 1 токен;
пробіли — 0; плюс {REQUEST_OVERHEAD_TOKENS} токенів на запит. Так враховано, що кирилиця дає більше токенів на символ,
ніж англійська, а UUID-подібні ідентифікатори дорогі.

Єдина точка калібрування — реальний виклик сесії `4fb003db` (2026-10-08): 4 репліки (52 слова
українською), 2 пункти порядку денного, тодішній системний промпт → **виміряно {cal.measured_input_tokens} вхідних і
{cal.measured_output_tokens} вихідних токенів**. Реконструкція цього запиту (тодішній формат промпта; текст
реплік синтетичний, бо справжній не зберігався: {cal.segments} репліки, {cal.words} слова, {cal.agenda_items} пункти) дає
**оцінку {cal.estimated_input_tokens} вхідних токенів ({cal.relative_error * 100:+.1f} % до виміру)**. Константи для кирилиці та латиниці
підібрано саме за цією точкою; одна точка не перевіряє розподіл між класами символів, тому
похибку на інших запитах слід вважати невідомою (орієнтовно десятки відсотків).

## 5. Результати (оцінка)

{render_tables(report)}

## 6. Що показують оцінки

{render_observations(report)}

Оцінки не суперечать припущенню, що головними чинниками вартості першої версії були ціна
моделі та частота викликів (гіпотеза H1 у частині кількості викликів), але **жодну гіпотезу
цим не підтверджено**: стенд не вимірює якість підказок (F1), справжні токени та справжню
затримку. Для цього потрібен платний реальний прогін (WP4) на тих самих сценаріях.

## 7. Обмеження

- **Оцінки, не виміри.** Вхідні токени — евристика, відкалібрована за однією точкою; вихідні
  токени — припущення (низ / верх), які не залежать від змісту розмови.
- **Немає метрики якості.** Заглушка не аналізує розмову; precision / recall / F1 підказок і
  частка відкинутих відповідей не оцінюються. Дешевша конфігурація може бути гіршою.
- **Синтетичні сценарії.** Рівний темп, повні речення, без перебивань, шуму та помилок
  розпізнавання; {len(report.scenarios)} сценаріїв, один колектив-шаблон, повторювані репліки в довгих сценаріях.
- **Заглушка LLM.** Відповідає миттєво й завжди успішно: немає часу відповіді моделі, помилок,
  таймаутів, обривів за `max_tokens`, розмикання запобіжника; повтори підказок майже не виникають.
- **Старі конфігурації неповні.** K0–K3 використовують поточний промпт і поточні параметри
  запиту (`thinking: disabled` передається завжди); «thinking увімкнено» для K0–K2 — лише
  припущення про розмір відповіді. Параметри «дозливу» після паузи для K0–K3 — поточні типові.
- **Кешування промпта й Batch API не моделюються.**
- **Затримка гейтингу ≠ затримка підказки.** Наскрізна затримка «подія → видима підказка»
  потребує вимірювань у розширенні та з реальною моделлю.
- **Ціни** взято з `server/core/cost.py` (сторінка Pricing, отримано 2026-10-08); перед
  цитуванням у роботі їх треба перевірити повторно.
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m server.eval.cost_replay",
        description="Offline LLM-cost replay (fake LLM, simulated time). All token and cost figures are estimates.",
    )
    parser.add_argument("--markdown", metavar="PATH", help="also write the full results document (Ukrainian) to PATH")
    args = parser.parse_args(argv)

    report = run_matrix()
    print("УСІ ТОКЕНИ Й ВАРТІСТЬ — ОЦІНКА (заглушка LLM, симульований час, синтетичні сценарії).")
    print(
        f"Калібрування: оцінка {CALIBRATION.estimated_input_tokens} проти виміряних "
        f"{CALIBRATION.measured_input_tokens} вхідних токенів ({CALIBRATION.relative_error * 100:+.1f} %).\n"
    )
    print(render_tables(report))

    if args.markdown:
        command = "server/.venv/bin/python -m server.eval.cost_replay --markdown " + args.markdown
        path = Path(args.markdown)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report, command), encoding="utf-8")
        print(f"\nЗаписано: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
