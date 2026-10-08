from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.agents.hint_generator import HintGenerator
from server.core.logging_config import (
    ConsoleFormatter,
    JsonFormatter,
    _ContextFilter,
    log_event,
    set_session_context,
)
from server.models import AgendaItem, AgendaState


def _record(event: str = "evt", **fields: object) -> logging.LogRecord:
    logger = logging.getLogger("server.test")
    rec = logger.makeRecord("server.test", logging.INFO, __file__, 1, event, (), None, extra=fields)
    _ContextFilter().filter(rec)
    return rec


class TestFormatters:
    def test_json_has_context_fields_and_redacts_sensitive_keys(self) -> None:
        set_session_context("sess-123", "meet-1")
        try:
            out = json.loads(
                JsonFormatter().format(_record(segment_id="s1", api_key="sk-ant-xyz", text="secret words"))
            )
        finally:
            set_session_context(None)
        assert out["event"] == "evt" and out["session"] == "sess-123" and out["meeting"] == "meet-1"
        assert out["segment_id"] == "s1"
        assert out["api_key"] == "[redacted]" and out["text"] == "[redacted]"

    def test_console_formatter_is_key_value(self) -> None:
        line = ConsoleFormatter(color=False).format(_record("llm_call", input_tokens=700, kind="hint"))
        assert "llm_call" in line and "input_tokens=700" in line and "kind=hint" in line

    def test_log_event_prefixes_reserved_field_names(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log_event(logging.getLogger("server.test"), "evt", name="x", message="y")
        rec = caplog.records[-1]
        assert rec.f_name == "x" and rec.f_message == "y"  # type: ignore[attr-defined]


class TestLlmCallEvent:
    @pytest.mark.asyncio
    async def test_llm_call_event_has_tokens_latency_and_no_transcript(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        gen = HintGenerator(api_key="k", model="claude-haiku-5-5")
        gen._client = SimpleNamespace(
            messages=SimpleNamespace(
                create=AsyncMock(
                    return_value=SimpleNamespace(
                        content=[SimpleNamespace(text="[]")],
                        usage=SimpleNamespace(input_tokens=700, output_tokens=40),
                        stop_reason="end_turn",
                    )
                )
            )
        )
        agenda = AgendaState(items=[AgendaItem(id="a", title="T", order=1)])
        with caplog.at_level(logging.INFO, logger="server.agents.hint_generator"):
            await gen.generate(agenda, "", [])
        rec = next(r for r in caplog.records if r.getMessage() == "llm_call")
        assert rec.input_tokens == 700 and rec.output_tokens == 40  # type: ignore[attr-defined]
        assert rec.stop_reason == "end_turn" and rec.latency_ms >= 0  # type: ignore[attr-defined]
        assert rec.session_cost_usd > 0  # type: ignore[attr-defined]
