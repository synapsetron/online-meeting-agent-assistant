"""Background (non-blocking) LLM hint call, idle flush and caps of the orchestrator.

The LLM is always faked via ``patch.object(orch._hint_gen, "generate", ...)``:
no API key is needed and no network call is made.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from server.agents.orchestrator import Orchestrator
from server.config import Config
from server.core.state_store import MeetingStateStore
from server.models import AgendaItem, Hint, HintType, TranscriptSegment


def _config(**overrides: Any) -> Config:
    base: dict[str, Any] = dict(
        anthropic_api_key="test-key",
        llm_debounce_seconds=0.0,
        llm_min_new_words=0,
        llm_flush_idle_seconds=0.0,  # idle flush off unless a test enables it
    )
    base.update(overrides)
    return Config(**base)


def _state() -> MeetingStateStore:
    return MeetingStateStore(
        meeting_id="m-1",
        agenda_items=[AgendaItem(id="ag-1", title="Budget review", order=1)],
        window_size=8,
    )


def _segment(idx: int, words: int = 5) -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg-{idx}", meeting_id="m-1", speaker_id="s-1",
        text=" ".join(["word"] * words), timestamp=float(idx), is_final=True,
    )


def _hint(hint_id: str = "h-1", hint_type: HintType = HintType.TOPIC_DRIFT) -> Hint:
    return Hint(
        id=hint_id, type=hint_type, agenda_item_id="ag-1", message="Back to the agenda",
        evidence_segment_ids=["seg-1"], confidence=0.9, timestamp=1.0,
    )


class _SlowLlm:
    """Fake ``HintGenerator.generate`` that blocks until released."""

    def __init__(self, hints: list[Hint]) -> None:
        self.hints = hints
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def __call__(self, **_: Any) -> list[Hint]:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return self.hints


def _events(caplog: pytest.LogCaptureFixture, name: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == name]


class TestBackgroundLlmCall:
    async def test_process_segment_returns_before_slow_llm_finishes(self) -> None:
        orch = Orchestrator(_config())
        llm = _SlowLlm([_hint()])
        with patch.object(orch._hint_gen, "generate", new=llm):
            result = await asyncio.wait_for(
                orch.process_segment(_segment(1), _state()), timeout=1.0
            )
            assert result.llm_triggered is True
            assert result.hints == []
            assert result.agenda_delta is not None

            await llm.started.wait()
            assert orch._llm_task is not None and not orch._llm_task.done()

            llm.release.set()
            assert [h.id for h in await orch.drain()] == ["h-1"]
            assert await orch.drain() == []  # repeatable, hints returned once
        await orch.aclose()

    async def test_hints_arrive_through_sink(self) -> None:
        orch = Orchestrator(_config())
        received: list[Hint] = []

        async def sink(hints: list[Hint]) -> None:
            received.extend(hints)

        orch.set_hint_sink(sink)
        with patch.object(orch._hint_gen, "generate", new=AsyncMock(return_value=[_hint()])):
            result = await orch.process_segment(_segment(1), _state())
            assert result.hints == []
            assert received == []  # not delivered inline
            assert await orch.drain() == []  # delivered to the sink, not stored
        assert [h.id for h in received] == ["h-1"]
        await orch.aclose()

    async def test_repeat_suppression_applies_to_background_hints(self) -> None:
        orch = Orchestrator(_config())
        state = _state()
        gen = AsyncMock(side_effect=[[_hint("h-1")], [_hint("h-2")]])
        with patch.object(orch._hint_gen, "generate", new=gen):
            await orch.process_segment(_segment(1), state)
            first = await orch.drain()
            await orch.process_segment(_segment(2), state)
            second = await orch.drain()
        assert [h.id for h in first] == ["h-1"]
        assert second == []  # same type + agenda item within the cooldown
        await orch.aclose()

    async def test_single_flight_skips_second_trigger(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        orch = Orchestrator(_config())
        state = _state()
        llm = _SlowLlm([])
        with (
            caplog.at_level(logging.DEBUG, logger="server.agents.orchestrator"),
            patch.object(orch._hint_gen, "generate", new=llm),
        ):
            first = await orch.process_segment(_segment(1), state)
            await llm.started.wait()
            second = await orch.process_segment(_segment(2), state)

            assert first.llm_triggered is True
            assert second.llm_triggered is False
            skipped = _events(caplog, "llm_skipped")
            assert [r.reason for r in skipped] == ["call_in_flight"]  # type: ignore[attr-defined]

            llm.release.set()
            await orch.drain()
        assert llm.calls == 1
        await orch.aclose()

    async def test_failing_llm_is_logged_and_session_continues(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        orch = Orchestrator(_config())
        state = _state()
        gen = AsyncMock(side_effect=[RuntimeError("boom"), [_hint()]])
        with (
            caplog.at_level(logging.ERROR, logger="server.agents.orchestrator"),
            patch.object(orch._hint_gen, "generate", new=gen),
        ):
            await orch.process_segment(_segment(1), state)
            assert await orch.drain() == []
            assert len(_events(caplog, "llm_background_failed")) == 1

            await orch.process_segment(_segment(2), state)
            assert [h.id for h in await orch.drain()] == ["h-1"]
        await orch.aclose()

    async def test_failing_sink_does_not_crash(self, caplog: pytest.LogCaptureFixture) -> None:
        orch = Orchestrator(_config())

        async def sink(hints: list[Hint]) -> None:
            raise RuntimeError("socket gone")

        orch.set_hint_sink(sink)
        with (
            caplog.at_level(logging.ERROR, logger="server.agents.orchestrator"),
            patch.object(orch._hint_gen, "generate", new=AsyncMock(return_value=[_hint()])),
        ):
            await orch.process_segment(_segment(1), _state())
            assert await orch.drain() == []
        assert len(_events(caplog, "llm_background_failed")) == 1
        await orch.aclose()


class TestIdleFlush:
    async def test_flush_fires_after_idle_period(self, caplog: pytest.LogCaptureFixture) -> None:
        # The per-segment gate needs 50 new words; the pause-triggered flush needs 3.
        orch = Orchestrator(_config(
            llm_min_new_words=50, llm_flush_idle_seconds=0.05, llm_flush_min_words=3,
        ))
        received: list[Hint] = []

        async def sink(hints: list[Hint]) -> None:
            received.extend(hints)

        orch.set_hint_sink(sink)
        gen = AsyncMock(return_value=[_hint()])
        with (
            caplog.at_level(logging.INFO, logger="server.agents.orchestrator"),
            patch.object(orch._hint_gen, "generate", new=gen),
        ):
            result = await orch.process_segment(_segment(1, words=5), _state())
            assert result.llm_triggered is False
            assert gen.await_count == 0

            await asyncio.sleep(0.2)
            await orch.drain()

        assert gen.await_count == 1
        assert [h.id for h in received] == ["h-1"]
        flushes = _events(caplog, "llm_flush")
        assert len(flushes) == 1
        assert flushes[0].pending_words == 5  # type: ignore[attr-defined]
        assert orch._pending_segments == []
        await orch.aclose()

    async def test_new_segment_rearms_the_timer(self) -> None:
        orch = Orchestrator(_config(
            llm_min_new_words=50, llm_flush_idle_seconds=0.15, llm_flush_min_words=3,
        ))
        state = _state()
        gen = AsyncMock(return_value=[])
        with patch.object(orch._hint_gen, "generate", new=gen):
            await orch.process_segment(_segment(1), state)
            timer = orch._flush_task
            await asyncio.sleep(0.1)
            await orch.process_segment(_segment(2), state)  # speech continues
            assert orch._flush_task is timer  # one timer task, deadline moved
            await asyncio.sleep(0.1)
            assert gen.await_count == 0  # 0.2 s since seg-1, only 0.1 s idle
            await asyncio.sleep(0.15)
            await orch.drain()
        assert gen.await_count == 1
        await orch.aclose()

    async def test_drain_runs_a_flush_that_is_already_due(self) -> None:
        orch = Orchestrator(_config(
            llm_min_new_words=50, llm_flush_idle_seconds=0.05, llm_flush_min_words=3,
        ))
        gen = AsyncMock(return_value=[_hint()])
        with patch.object(orch._hint_gen, "generate", new=gen):
            await orch.process_segment(_segment(1), _state())
            assert await orch.drain() == []  # not due yet: drain does not wait for it
            assert gen.await_count == 0
            time.sleep(0.06)  # block the loop so the timer task cannot run first
            assert [h.id for h in await orch.drain()] == ["h-1"]
        await orch.aclose()

    async def test_flush_skipped_when_too_few_words(self, caplog: pytest.LogCaptureFixture) -> None:
        orch = Orchestrator(_config(
            llm_min_new_words=50, llm_flush_idle_seconds=0.03, llm_flush_min_words=12,
        ))
        gen = AsyncMock(return_value=[])
        with (
            caplog.at_level(logging.DEBUG, logger="server.agents.orchestrator"),
            patch.object(orch._hint_gen, "generate", new=gen),
        ):
            await orch.process_segment(_segment(1, words=5), _state())
            await asyncio.sleep(0.12)
        assert gen.await_count == 0
        skipped = [
            r for r in _events(caplog, "llm_skipped")
            if r.trigger == "idle_flush"  # type: ignore[attr-defined]
        ]
        assert [r.reason for r in skipped] == ["too_few_new_words"]  # type: ignore[attr-defined]
        assert orch._flush_task is not None and orch._flush_task.done()
        await orch.aclose()

    async def test_flush_waits_for_min_interval(self) -> None:
        orch = Orchestrator(_config(
            llm_debounce_seconds=0.25, llm_flush_idle_seconds=0.05, llm_flush_min_words=3,
        ))
        state = _state()
        gen = AsyncMock(return_value=[])
        with patch.object(orch._hint_gen, "generate", new=gen):
            # Simulate a call that has just been made.
            orch._last_llm_call_time = time.monotonic()
            await orch.process_segment(_segment(1), state)
            await asyncio.sleep(0.12)  # idle period over, minimum interval not
            assert gen.await_count == 0
            await asyncio.sleep(0.25)
            await orch.drain()
        assert gen.await_count == 1
        await orch.aclose()

    async def test_flush_respects_call_cap(self) -> None:
        orch = Orchestrator(_config(
            llm_min_new_words=50, llm_flush_idle_seconds=0.03, llm_flush_min_words=3,
            llm_max_calls_per_session=0,
        ))
        gen = AsyncMock(return_value=[])
        with patch.object(orch._hint_gen, "generate", new=gen):
            await orch.process_segment(_segment(1), _state())
            await asyncio.sleep(0.1)
            await orch.drain()
        assert gen.await_count == 0
        assert orch._last_skip_reason == "call_cap_reached"
        await orch.aclose()


class TestClose:
    async def test_aclose_cancels_in_flight_call_and_timer(self) -> None:
        orch = Orchestrator(_config(llm_flush_idle_seconds=30.0, llm_flush_min_words=1))
        state = _state()
        llm = _SlowLlm([_hint()])
        delivered: list[Hint] = []

        async def sink(hints: list[Hint]) -> None:
            delivered.extend(hints)

        orch.set_hint_sink(sink)
        with patch.object(orch._hint_gen, "generate", new=llm):
            await orch.process_segment(_segment(1), state)
            await llm.started.wait()
            await orch.process_segment(_segment(2), state)  # in flight: arms the timer
            llm_task, flush_task = orch._llm_task, orch._flush_task
            assert llm_task is not None and flush_task is not None

            await asyncio.wait_for(orch.aclose(), timeout=1.0)

            assert llm_task.cancelled()
            assert flush_task.cancelled()
            assert delivered == []
            assert await orch.drain() == []
            await orch.aclose()  # idempotent

    async def test_late_result_after_close_is_dropped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A provider call that ignores cancellation still returns after the
        session ended; its hints must go nowhere."""
        orch = Orchestrator(_config())
        started = asyncio.Event()
        delivered: list[Hint] = []

        async def stubborn_llm(**_: Any) -> list[Hint]:
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                pass
            return [_hint()]

        async def sink(hints: list[Hint]) -> None:
            delivered.extend(hints)

        orch.set_hint_sink(sink)
        with (
            caplog.at_level(logging.INFO, logger="server.agents.orchestrator"),
            patch.object(orch._hint_gen, "generate", new=stubborn_llm),
        ):
            await orch.process_segment(_segment(1), _state())
            await started.wait()
            await asyncio.wait_for(orch.aclose(), timeout=1.0)

        assert delivered == []
        assert await orch.drain() == []
        dropped = _events(caplog, "llm_result_dropped")
        assert [r.reason for r in dropped] == ["session_closed"]  # type: ignore[attr-defined]


class TestCaps:
    async def test_call_cap_stops_background_calls(self) -> None:
        orch = Orchestrator(_config(llm_max_calls_per_session=2))
        state = _state()
        gen = AsyncMock(return_value=[])
        with patch.object(orch._hint_gen, "generate", new=gen):
            triggered = []
            for i in range(5):
                result = await orch.process_segment(_segment(i), state)
                triggered.append(result.llm_triggered)
                await orch.drain()
        assert triggered == [True, True, False, False, False]
        assert gen.await_count == 2
        assert orch._last_skip_reason == "call_cap_reached"
        await orch.aclose()

    async def test_cost_cap_stops_background_calls(self) -> None:
        orch = Orchestrator(_config(
            llm_max_session_cost_usd=0.001, anthropic_model="claude-haiku-5-5",
        ))
        state = _state()

        async def costly_llm(**_: Any) -> list[Hint]:
            # What a real call would have recorded: 10k output tokens = $0.005.
            orch.usage.output_tokens += 10_000
            return []

        gen = AsyncMock(side_effect=costly_llm)
        with patch.object(orch._hint_gen, "generate", new=gen):
            first = await orch.process_segment(_segment(1), state)
            await orch.drain()
            second = await orch.process_segment(_segment(2), state)
            await orch.drain()
        assert (first.llm_triggered, second.llm_triggered) == (True, False)
        assert gen.await_count == 1
        assert orch._last_skip_reason == "cost_cap_reached"
        await orch.aclose()

    def test_default_caps_are_a_budget(self) -> None:
        cfg = Config(anthropic_api_key="k")
        assert cfg.llm_max_calls_per_session == 200
        assert cfg.llm_max_session_cost_usd == 0.05
        assert cfg.llm_flush_idle_seconds == 20.0
        assert cfg.llm_flush_min_words == 12


class TestWebSocketBackgroundHints:
    """Gateway wiring: a hint produced in the background reaches the client."""

    _CONNECT = {
        "type": "CONNECT", "meetingId": "m-1", "title": "T", "participants": [],
        "agendaItems": [{"id": "ag-1", "title": "Budget review", "order": 1}],
    }
    _SEGMENT = {
        "type": "TRANSCRIPT",
        "segment": {
            "id": "seg-1", "meetingId": "m-1", "speakerId": "s-1",
            "text": " ".join(["word"] * 60), "timestamp": 1.0, "isFinal": True,
        },
    }

    def test_new_hint_pushed_after_transcript_echo(self) -> None:
        from fastapi.testclient import TestClient

        from server.agents.hint_generator import HintGenerator
        from server.main import app

        async def fake_generate(self: Any, **_: Any) -> list[Hint]:
            await asyncio.sleep(0.05)
            return [_hint("h-bg")]

        with (
            patch.object(HintGenerator, "generate", new=fake_generate),
            TestClient(app) as client,
            client.websocket_connect("/ws") as ws,
        ):
            ws.send_json(self._CONNECT)
            assert ws.receive_json()["type"] == "SESSION_ACK"
            ws.send_json(self._SEGMENT)
            assert ws.receive_json()["type"] == "NEW_TRANSCRIPT"  # not delayed by the LLM
            message = ws.receive_json()
            assert message["type"] == "NEW_HINT"
            assert message["hint"]["id"] == "h-bg"

    def test_audio_stop_delivers_in_flight_hint_before_summary(self) -> None:
        from fastapi.testclient import TestClient

        from server.agents.hint_generator import HintGenerator
        from server.main import app

        async def fake_generate(self: Any, **_: Any) -> list[Hint]:
            await asyncio.sleep(0.1)
            return [_hint("h-bg")]

        with (
            patch.object(HintGenerator, "generate", new=fake_generate),
            TestClient(app) as client,
            client.websocket_connect("/ws") as ws,
        ):
            ws.send_json(self._CONNECT)
            ws.receive_json()
            ws.send_json(self._SEGMENT)
            assert ws.receive_json()["type"] == "NEW_TRANSCRIPT"
            ws.send_json({"type": "AUDIO_STOP"})
            assert [ws.receive_json()["type"] for _ in range(2)] == [
                "NEW_HINT", "MEETING_SUMMARY",
            ]


class TestRepeatAvoidance:
    @pytest.mark.asyncio
    async def test_time_warning_for_same_item_is_not_repeated_every_segment(self) -> None:
        from server.models import AgendaItemStatus

        cfg = Config(anthropic_api_key="k", llm_max_calls_per_session=0, llm_flush_idle_seconds=0)
        orch = Orchestrator(config=cfg)
        state = MeetingStateStore(
            "m", [AgendaItem(id="a", title="Topic", order=1, estimated_minutes=1)], 8
        )
        state.agenda.items[0].status = AgendaItemStatus.ACTIVE
        state.agenda.items[0].elapsed_seconds = 500
        state.agenda.active_item_id = "a"
        counts = []
        for i in range(4):
            seg = TranscriptSegment(
                id=f"s{i}", meeting_id="m", speaker_id="u", text="one two three four",
                timestamp=1000.0 + i, is_final=True,
            )
            counts.append(len((await orch.process_segment(seg, state)).time_warnings))
        await orch.aclose()
        assert counts == [1, 0, 0, 0]

    def test_recently_shown_hints_are_listed_in_prompt_by_alias(self) -> None:
        from server.agents.hint_generator import _build_user_content
        from server.models import AgendaState

        agenda = AgendaState(items=[AgendaItem(id="item-long-id", title="Topic", order=1)])
        seg = TranscriptSegment(
            id="uuid-1", meeting_id="m", speaker_id="u", text="hello there", timestamp=1.0, is_final=True
        )
        with_shown = _build_user_content(agenda, "", [seg], [("topic_drift", "item-long-id")])
        assert "Shown: topic_drift a1" in with_shown
        assert "item-long-id" not in with_shown
        assert "Shown" not in _build_user_content(agenda, "", [seg])
