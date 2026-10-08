from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.agents.hint_generator import (
    _SYSTEM_PROMPT,
    HintGenerator,
    _build_aliases,
    _build_user_content,
    _parse_hints,
)
from server.config import Config
from server.core.circuit_breaker import CircuitState
from server.models import (
    AgendaItem,
    AgendaItemStatus,
    AgendaState,
    HintType,
    TranscriptSegment,
)


def _agenda() -> AgendaState:
    return AgendaState(
        items=[
            AgendaItem(id="ag-1", title="Topic A", order=1, estimated_minutes=5),
        ],
        start_time=0.0,
    )


def _segment(idx: int = 0) -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg-{idx}",
        meeting_id="m-1",
        speaker_id="s-1",
        text=f"text {idx}",
        timestamp=float(idx),
        is_final=True,
    )


class TestHintGeneratorCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_consecutive_failures(self) -> None:
        gen = HintGenerator(api_key="test", model="test", timeout=5.0)
        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(
            side_effect=Exception("API error")
        )

        for _ in range(3):
            result = await gen.generate(_agenda(), "", [_segment()])
            assert result == []

        assert gen._circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_skips_call_when_circuit_open(self) -> None:
        gen = HintGenerator(api_key="test", model="test", timeout=5.0)
        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(
            side_effect=Exception("API error")
        )

        # Open the circuit
        for _ in range(3):
            await gen.generate(_agenda(), "", [_segment()])

        # Reset the mock to verify no more calls are made
        gen._client.messages.create.reset_mock()
        result = await gen.generate(_agenda(), "", [_segment()])
        assert result == []
        gen._client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_closes_on_success(self) -> None:
        gen = HintGenerator(api_key="test", model="test", timeout=5.0)

        # Start with a successful call
        mock_block = type("Block", (), {"text": "[]"})()
        mock_response = type("Response", (), {"content": [mock_block]})()
        gen._client = AsyncMock()
        gen._client.messages.create = AsyncMock(return_value=mock_response)

        result = await gen.generate(_agenda(), "", [_segment()])
        assert gen._circuit_breaker.state == CircuitState.CLOSED


class TestConfigModelId:
    def test_default_model_is_current(self) -> None:
        config = Config()
        assert config.anthropic_model == "claude-haiku-5-5"


class TestCostControls:
    def test_usage_meter_estimates_cost_from_published_rates(self) -> None:
        from types import SimpleNamespace

        from server.core.cost import UsageMeter

        meter = UsageMeter(model="claude-haiku-5-5")
        meter.record(SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000))
        assert meter.cost_usd == pytest.approx(0.60)  # $0.10 in + $0.50 out per MTok
        assert UsageMeter(model="unknown-model").cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_request_disables_thinking_and_records_usage(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        gen = HintGenerator(api_key="k", model="claude-haiku-5-5")
        create = AsyncMock(
            return_value=SimpleNamespace(
                content=[SimpleNamespace(text="[]")],
                usage=SimpleNamespace(input_tokens=500, output_tokens=20),
            )
        )
        gen._client = SimpleNamespace(messages=SimpleNamespace(create=create))
        agenda = AgendaState(items=[AgendaItem(id="a", title="T", order=1)])
        await gen.generate(agenda, "", [])
        kwargs = create.await_args.kwargs
        assert kwargs["thinking"] == {"type": "disabled"}
        assert kwargs["output_config"] == {"effort": "low"}
        assert gen.usage.input_tokens == 500 and gen.usage.calls == 1


# --- WP1: id aliasing, compact schema, shorter prompt -------------------------

# Frozen copy of the prompt format used before WP1. Baseline for the size
# comparison only; it is not used by the application.
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


def _legacy_user_content(
    agenda: AgendaState, rolling_summary: str, recent_segments: list[TranscriptSegment]
) -> str:
    agenda_lines = []
    for item in agenda.items:
        est = f"est {item.estimated_minutes}min" if item.estimated_minutes else "no estimate"
        agenda_lines.append(
            f"- [{item.status.value}] {item.id}: {item.title} "
            f"({item.elapsed_seconds:.0f}s elapsed, {est})"
        )
    agenda_block = "\n".join(agenda_lines)
    transcript_block = "\n".join(f"[{seg.id}] {seg.text[:300]}" for seg in recent_segments)
    return (
        f"Current agenda state:\n{agenda_block}\n\n"
        f"Active item: {agenda.active_item_id or 'none'}\n\n"
        + (f"Rolling summary:\n{rolling_summary[:800]}\n\n" if rolling_summary else "")
        + f"Recent transcript:\n<transcript>\n{transcript_block}\n</transcript>\n\n"
        "Generate hints as a JSON array."
    )


_ITEM_IDS = ["item-1791006808101-scy4", "item-1791006808102-k9qd", "item-1791006808103-m2xz"]
_SEGMENT_IDS = [
    "366e67a9-89ac-436b-8920-f15a9d739f7b",
    "0b1f5c3e-7a42-4d8e-9c61-2e4a7f9b1d05",
    "a4d2e8f1-3b6c-4f7a-8e29-5c1d0b9a7e63",
    "7e9c1a2b-4d5f-4a6b-9c8d-1f2e3a4b5c6d",
    "c3b2a190-8f7e-4d6c-b5a4-392817161514",
    "5f6e7d8c-9b0a-4c1d-8e2f-3a4b5c6d7e8f",
    "12345678-90ab-4cde-8f01-23456789abcd",
    "fedcba98-7654-4321-8fed-cba987654321",
]
_SEGMENT_TEXTS = [
    "Добрий день, колеги, починаємо зустріч.",
    "Перше питання — стан розробки серверної частини.",
    "Оркестратор і три агенти вже працюють, тести проходять.",
    "Залишилось виміряти затримку від сегмента до підказки.",
    "До речі, хто дивився вчорашній футбол?",
    "Так, матч був чудовий, особливо другий тайм.",
    "Я думаю, наступного тижня теж варто піти на стадіон.",
    "Квитки можна купити онлайн, я надішлю посилання.",
]


def _fixture() -> tuple[AgendaState, list[TranscriptSegment]]:
    agenda = AgendaState(
        items=[
            AgendaItem(
                id=_ITEM_IDS[0], title="Стан розробки бекенду", order=1,
                estimated_minutes=10, status=AgendaItemStatus.ACTIVE, elapsed_seconds=240.0,
            ),
            AgendaItem(id=_ITEM_IDS[1], title="План експериментів", order=2, estimated_minutes=15),
            AgendaItem(id=_ITEM_IDS[2], title="Терміни подання роботи", order=3),
        ],
        active_item_id=_ITEM_IDS[0],
        start_time=0.0,
    )
    segments = [
        TranscriptSegment(
            id=seg_id, meeting_id="m-1", speaker_id="s-1",
            text=text, timestamp=float(i), is_final=True,
        )
        for i, (seg_id, text) in enumerate(zip(_SEGMENT_IDS, _SEGMENT_TEXTS))
    ]
    return agenda, segments


def _parse_with_aliases(raw: str, agenda: AgendaState, segments: list[TranscriptSegment]):
    item_aliases, segment_aliases = _build_aliases(agenda, segments)
    return _parse_hints(
        raw,
        {item.id for item in agenda.items},
        {seg.id for seg in segments},
        agenda.active_item_id,
        item_aliases=item_aliases,
        segment_aliases=segment_aliases,
    )


class TestPromptAliasing:
    def test_prompt_uses_aliases_and_never_real_ids(self) -> None:
        agenda, segments = _fixture()
        content = _build_user_content(agenda, "", segments)

        for real_id in _ITEM_IDS + _SEGMENT_IDS:
            assert real_id not in content
        assert "a1 [active] Стан розробки бекенду (240s of 10min)" in content
        assert "a3 [pending] Терміни подання роботи (0s)" in content
        assert "Active: a1" in content
        assert f"s1: {_SEGMENT_TEXTS[0]}" in content
        assert f"s8: {_SEGMENT_TEXTS[7]}" in content

    def test_transcript_is_last_and_xml_delimited(self) -> None:
        agenda, segments = _fixture()
        content = _build_user_content(agenda, "Раніше обговорили план.", segments)

        assert content.endswith("</transcript>")
        assert content.index("Agenda:") < content.index("Summary:") < content.index("<transcript>")
        assert "<transcript>" not in _SYSTEM_PROMPT.replace("inside <transcript>", "")

    def test_aliases_follow_input_order(self) -> None:
        agenda, segments = _fixture()
        item_aliases, segment_aliases = _build_aliases(agenda, segments)

        assert item_aliases == {"a1": _ITEM_IDS[0], "a2": _ITEM_IDS[1], "a3": _ITEM_IDS[2]}
        assert list(segment_aliases.items())[:2] == [("s1", _SEGMENT_IDS[0]), ("s2", _SEGMENT_IDS[1])]
        assert len(segment_aliases) == 8

    def test_no_active_item(self) -> None:
        agenda, segments = _fixture()
        agenda.active_item_id = None
        assert "Active: none" in _build_user_content(agenda, "", segments)

    def test_system_prompt_keeps_correctness_rules(self) -> None:
        for hint_type in HintType:
            assert hint_type.value in _SYSTEM_PROMPT
        for needle in ('"t"', '"a"', '"m"', '"e"', '"c"', "[]", "20 words", "At most 2", "code fences"):
            assert needle in _SYSTEM_PROMPT
        assert "uncertainty" not in _SYSTEM_PROMPT


class TestParseCompactHints:
    def test_aliases_are_mapped_back_to_real_ids(self) -> None:
        agenda, segments = _fixture()
        raw = json.dumps(
            [{"t": "topic_drift", "a": "a1", "m": "Поверніться до бекенду.", "e": ["s5", "s6"], "c": 0.8}],
            ensure_ascii=False,
        )
        hints = _parse_with_aliases(raw, agenda, segments)

        assert len(hints) == 1
        hint = hints[0]
        assert hint.type is HintType.TOPIC_DRIFT
        assert hint.agenda_item_id == _ITEM_IDS[0]
        assert hint.evidence_segment_ids == [_SEGMENT_IDS[4], _SEGMENT_IDS[5]]
        assert hint.message == "Поверніться до бекенду."
        assert hint.confidence == pytest.approx(0.8)
        assert hint.uncertainty is None

    def test_code_fenced_answer_is_still_parsed(self) -> None:
        agenda, segments = _fixture()
        raw = '```json\n[{"t":"summary","a":"a2","m":"ok","e":["s1"],"c":1}]\n```'
        hints = _parse_with_aliases(raw, agenda, segments)
        assert [h.agenda_item_id for h in hints] == [_ITEM_IDS[1]]

    def test_unknown_item_alias_is_rejected(self) -> None:
        agenda, segments = _fixture()
        raw = '[{"t":"agenda_suggestion","a":"a9","m":"x","e":["s1"],"c":0.9}]'
        assert _parse_with_aliases(raw, agenda, segments) == []

    def test_unknown_item_alias_on_drift_falls_back_to_active_item(self) -> None:
        agenda, segments = _fixture()
        raw = '[{"t":"topic_drift","a":"a9","m":"x","e":["s5"],"c":0.9}]'
        hints = _parse_with_aliases(raw, agenda, segments)
        assert [h.agenda_item_id for h in hints] == [_ITEM_IDS[0]]

    def test_unknown_evidence_aliases_are_filtered_and_empty_evidence_drops_hint(self) -> None:
        agenda, segments = _fixture()
        raw = (
            '[{"t":"summary","a":"a1","m":"kept","e":["s2","s99"],"c":0.9},'
            ' {"t":"summary","a":"a1","m":"dropped","e":["s99"],"c":0.9},'
            ' {"t":"summary","a":"a1","m":"dropped too","e":[],"c":0.9}]'
        )
        hints = _parse_with_aliases(raw, agenda, segments)
        assert [(h.message, h.evidence_segment_ids) for h in hints] == [("kept", [_SEGMENT_IDS[1]])]

    def test_old_long_key_format_with_real_ids_still_works(self) -> None:
        agenda, segments = _fixture()
        raw = json.dumps([{
            "type": "missed_item",
            "agenda_item_id": _ITEM_IDS[2],
            "message": "Не обговорено терміни.",
            "evidence_segment_ids": [_SEGMENT_IDS[7]],
            "confidence": 0.6,
            "uncertainty": "maybe later",
        }])
        hints = _parse_with_aliases(raw, agenda, segments)

        assert len(hints) == 1
        assert hints[0].agenda_item_id == _ITEM_IDS[2]
        assert hints[0].evidence_segment_ids == [_SEGMENT_IDS[7]]
        assert hints[0].uncertainty is None

    def test_positional_call_without_alias_maps_still_works(self) -> None:
        raw = '[{"type":"summary","agenda_item_id":"ag-1","message":"m","evidence_segment_ids":["seg-0"]}]'
        hints = _parse_hints(raw, {"ag-1"}, {"seg-0"}, "ag-1")
        assert len(hints) == 1 and hints[0].confidence == 0.5
        # Without alias maps an alias is just an unknown id.
        assert _parse_hints('[{"t":"summary","a":"a1","m":"m","e":["s1"]}]', {"ag-1"}, {"seg-0"}) == []

    def test_at_most_two_hints_are_accepted(self) -> None:
        agenda, segments = _fixture()
        raw = json.dumps([
            {"t": "summary", "a": "a1", "m": f"m{i}", "e": ["s1"], "c": 0.5} for i in range(4)
        ])
        assert [h.message for h in _parse_with_aliases(raw, agenda, segments)] == ["m0", "m1"]

    def test_malformed_entries_are_skipped(self) -> None:
        agenda, segments = _fixture()
        raw = (
            '["text", {"t":"nonsense","a":"a1","m":"x","e":["s1"]},'
            ' {"t":"summary","a":["a1"],"m":"x","e":["s1"]},'
            ' {"t":"summary","a":"a1","m":"  ","e":["s1"]},'
            ' {"t":"summary","a":"a1","m":"x","e":{"s1":1}},'
            ' {"t":"summary","a":"a1","m":"good","e":"s1","c":"high"}]'
        )
        hints = _parse_with_aliases(raw, agenda, segments)
        assert [(h.message, h.confidence) for h in hints] == [("good", 0.5)]
        assert _parse_with_aliases("no json here", agenda, segments) == []
        assert _parse_with_aliases("[not json]", agenda, segments) == []


class TestGenerateWithAliases:
    @pytest.mark.asyncio
    async def test_generate_sends_aliases_and_returns_real_ids(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agenda, segments = _fixture()
        message = "Розмова відійшла від теми бекенду."
        answer = json.dumps(
            [{"t": "topic_drift", "a": "a1", "m": message, "e": ["s5", "s7"], "c": 0.9}],
            ensure_ascii=False,
        )
        create = AsyncMock(
            return_value=SimpleNamespace(
                content=[SimpleNamespace(text=answer)],
                usage=SimpleNamespace(input_tokens=400, output_tokens=40),
                stop_reason="end_turn",
            )
        )
        gen = HintGenerator(api_key="k", model="claude-haiku-5-5")
        gen._client = SimpleNamespace(messages=SimpleNamespace(create=create))

        with caplog.at_level(logging.INFO, logger="server.agents.hint_generator"):
            hints = await gen.generate(agenda, "", segments)

        kwargs = create.await_args.kwargs
        assert kwargs["system"] == _SYSTEM_PROMPT
        sent = kwargs["messages"][0]["content"]
        assert kwargs["messages"][0]["role"] == "user"
        assert all(real_id not in sent for real_id in _ITEM_IDS + _SEGMENT_IDS)

        assert len(hints) == 1
        assert hints[0].agenda_item_id == _ITEM_IDS[0]
        assert hints[0].evidence_segment_ids == [_SEGMENT_IDS[4], _SEGMENT_IDS[6]]
        assert gen.usage.calls == 1 and gen.usage.output_tokens == 40

        # Neither transcript text nor the hint message may reach the logs.
        logged = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
        assert message not in logged
        assert all(text not in logged for text in _SEGMENT_TEXTS)


class TestPromptSize:
    """Character counts are a proxy for tokens, not a token or cost measurement."""

    def test_new_prompt_is_meaningfully_smaller_than_legacy(self) -> None:
        agenda, segments = _fixture()

        old_system, new_system = len(_LEGACY_SYSTEM_PROMPT), len(_SYSTEM_PROMPT)
        old_user = len(_legacy_user_content(agenda, "", segments))
        new_user = len(_build_user_content(agenda, "", segments))
        old_total, new_total = old_system + old_user, new_system + new_user
        reduction = 1 - new_total / old_total

        # One drift hint citing two segments, same message, both answer formats.
        message = "Розмова відійшла від теми бекенду, поверніться до порядку денного."
        old_answer = json.dumps([{
            "type": "topic_drift", "agenda_item_id": _ITEM_IDS[0], "message": message,
            "evidence_segment_ids": [_SEGMENT_IDS[4], _SEGMENT_IDS[5]],
            "confidence": 0.9, "uncertainty": None,
        }], ensure_ascii=False)
        new_answer = json.dumps(
            [{"t": "topic_drift", "a": "a1", "m": message, "e": ["s5", "s6"], "c": 0.9}],
            ensure_ascii=False, separators=(",", ":"),
        )

        print(
            f"\nWP1 prompt size (chars): system {old_system} -> {new_system}, "
            f"user {old_user} -> {new_user}, total {old_total} -> {new_total} "
            f"({reduction:.1%} smaller); answer {len(old_answer)} -> {len(new_answer)} "
            f"({1 - len(new_answer) / len(old_answer):.1%} smaller)"
        )

        assert new_system < old_system
        assert new_user < old_user
        assert reduction >= 0.25
        assert len(new_answer) < 0.6 * len(old_answer)
