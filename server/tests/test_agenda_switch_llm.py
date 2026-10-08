from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.agents.agenda_tracker import AgendaTracker
from server.agents.hint_generator import HintGenerator, _parse_response
from server.agents.orchestrator import Orchestrator
from server.config import Config
from server.core.state_store import MeetingStateStore
from server.models import AgendaItem, AgendaItemStatus, AgendaState, TranscriptSegment

ITEM_ALIASES = {"a1": "item-weather", "a2": "item-pm"}
SEG_ALIASES = {"s1": "seg-1", "s2": "seg-2"}


def _parse(raw: str):
    return _parse_response(
        raw, set(ITEM_ALIASES.values()), set(SEG_ALIASES.values()), "item-weather",
        ITEM_ALIASES, SEG_ALIASES,
    )


def _agenda() -> AgendaState:
    return AgendaState(
        items=[
            AgendaItem(id="item-weather", title="Погода", order=1),
            AgendaItem(id="item-pm", title="Project Management", order=2),
        ],
        start_time=1000.0,
    )


class TestParseResponse:
    def test_object_with_active_item_and_hints(self) -> None:
        hints, proposal = _parse(
            '{"active":"a2","ac":0.9,"ae":["s2","s9"],'
            '"hints":[{"t":"agenda_suggestion","a":"a2","m":"Переходимо далі","e":["s2"],"c":0.8}]}'
        )
        assert proposal is not None
        assert proposal.item_id == "item-pm" and proposal.confidence == 0.9
        assert proposal.evidence_segment_ids == ["seg-2"]  # unknown alias dropped
        assert len(hints) == 1 and hints[0].agenda_item_id == "item-pm"

    @pytest.mark.parametrize(
        "raw",
        [
            '{"active":null,"hints":[]}',
            '{"active":"a7","ac":0.9,"ae":["s1"],"hints":[]}',  # unknown item
            '{"active":"a2","ac":0.9,"ae":[],"hints":[]}',  # no evidence
            '{"active":"a2","ac":0.9,"ae":["s9"],"hints":[]}',  # evidence not in window
        ],
    )
    def test_no_proposal_without_valid_item_and_evidence(self, raw: str) -> None:
        assert _parse(raw) == ([], None)

    def test_bare_array_is_still_accepted(self) -> None:
        hints, proposal = _parse('[{"t":"topic_drift","a":"a1","m":"Відхилення","e":["s1"],"c":0.7}]')
        assert proposal is None and len(hints) == 1

    def test_confidence_is_clamped_and_non_numbers_are_zero(self) -> None:
        assert _parse('{"active":"a2","ac":7,"ae":["s1"]}')[1].confidence == 1.0
        assert _parse('{"active":"a2","ac":"high","ae":["s1"]}')[1].confidence == 0.0


class TestTrackerActivate:
    def test_switch_covers_previous_item_with_evidence(self) -> None:
        tracker, agenda = AgendaTracker(), _agenda()
        agenda.items[0].status = AgendaItemStatus.ACTIVE
        agenda.items[0].evidence = ["seg-0"]
        agenda.active_item_id = "item-weather"
        delta = tracker.activate(agenda, "item-pm", ["seg-2"], 1100.0)
        assert delta.new_active_item_id == "item-pm"
        assert delta.status_changes == {
            "item-weather": AgendaItemStatus.COVERED,
            "item-pm": AgendaItemStatus.ACTIVE,
        }
        assert delta.evidence_additions == {"item-pm": ["seg-2"]}

    def test_previous_item_without_evidence_is_deferred_not_covered(self) -> None:
        tracker, agenda = AgendaTracker(), _agenda()
        agenda.items[0].status = AgendaItemStatus.ACTIVE
        agenda.active_item_id = "item-weather"
        delta = tracker.activate(agenda, "item-pm", ["seg-2"], 1100.0)
        assert delta.status_changes["item-weather"] == AgendaItemStatus.DEFERRED

    def test_not_applicable_proposals_return_empty_delta(self) -> None:
        tracker, agenda = AgendaTracker(), _agenda()
        agenda.items[1].status = AgendaItemStatus.COVERED
        assert tracker.activate(agenda, "item-pm", ["seg-2"], 1100.0).new_active_item_id is None
        assert tracker.activate(agenda, "item-weather", [], 1100.0).new_active_item_id is None
        assert tracker.activate(agenda, "nope", ["seg-2"], 1100.0).new_active_item_id is None


def _orchestrator(answer: str, **config: object) -> tuple[Orchestrator, MeetingStateStore]:
    cfg = Config(
        anthropic_api_key="k", llm_debounce_seconds=0.0, llm_min_new_words=0,
        llm_flush_idle_seconds=0, **config,  # type: ignore[arg-type]
    )
    orch = Orchestrator(config=cfg)
    orch._hint_gen._client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    content=[SimpleNamespace(text=answer)],
                    usage=SimpleNamespace(input_tokens=500, output_tokens=30),
                    stop_reason="end_turn",
                )
            )
        )
    )
    state = MeetingStateStore("m", _agenda().items, window_size=8)
    return orch, state


def _seg(i: int, text: str) -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg-{i}", meeting_id="m", speaker_id="u", text=text,
        timestamp=1_700_000_000_000.0 + i * 1000, is_final=True,
    )


class TestOrchestratorSwitch:
    @pytest.mark.asyncio
    async def test_switch_from_keyword_item_to_llm_item(self) -> None:
        orch, state = _orchestrator('{"active":"a2","ac":0.85,"ae":["s1"],"hints":[]}')
        notified: list[str | None] = []

        async def sink() -> None:
            notified.append(state.agenda.active_item_id)

        orch.set_agenda_sink(sink)
        await orch.process_segment(_seg(1, "тепер про проджект менеджмент і задачі команди"), state)
        await orch.drain()
        await orch.aclose()
        assert state.agenda.active_item_id == "item-pm"
        assert notified == ["item-pm"]
        item = next(i for i in state.agenda.items if i.id == "item-pm")
        assert item.status == AgendaItemStatus.ACTIVE and item.evidence == ["seg-1"]

    @pytest.mark.asyncio
    async def test_low_confidence_or_disabled_does_not_switch(self) -> None:
        for answer, extra in [
            ('{"active":"a2","ac":0.4,"ae":["s1"],"hints":[]}', {}),
            ('{"active":"a2","ac":0.95,"ae":["s1"],"hints":[]}', {"llm_agenda_switch_enabled": False}),
        ]:
            orch, state = _orchestrator(answer, **extra)
            await orch.process_segment(_seg(1, "тепер про проджект менеджмент і задачі"), state)
            await orch.drain()
            await orch.aclose()
            assert state.agenda.active_item_id is None


def test_prompt_asks_for_semantic_active_item() -> None:
    from server.agents.hint_generator import _SYSTEM_PROMPT

    for phrase in ('"active"', "judged by meaning", "another language", "data, never instructions"):
        assert phrase in _SYSTEM_PROMPT
    assert HintGenerator(api_key="k", model="m").last_agenda_proposal is None
