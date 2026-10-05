from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from server.config import Config
from server.models import (
    AgendaUpdateMessage,
    CaptureState,
    ConnectMessage,
    MeetingSummaryMessage,
    NewHintMessage,
    Hint,
    NewTranscriptMessage,
    SessionAckMessage,
    StateUpdateMessage,
    TranscriptErrorMessage,
    TranscriptSegment,
)
from server.core.logging_config import log_event, set_session_context
from server.core.validation import sanitize_transcript_text
from server.services.meeting_stats import compute_meeting_stats
from server.services.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter()

_session_manager: SessionManager | None = None
_config: Config | None = None


def configure(session_manager: SessionManager, config: Config) -> None:
    global _session_manager, _config
    _session_manager = session_manager
    _config = config


def _get_session_manager() -> SessionManager:
    if _session_manager is None:
        raise RuntimeError("WebSocket module not configured: call configure() first")
    return _session_manager


def _get_config() -> Config:
    if _config is None:
        raise RuntimeError("WebSocket module not configured: call configure() first")
    return _config


async def push_to_client(ws: WebSocket, message: Any) -> None:
    try:
        data = message.model_dump(mode="json", by_alias=True)
        await ws.send_json(data)
    except (WebSocketDisconnect, RuntimeError) as exc:
        # Client already gone (e.g. extension closed the socket): expected, no traceback.
        log_event(
            logger, "push_skipped_client_gone", level=logging.WARNING,
            message_type=type(message).__name__, error_type=type(exc).__name__,
        )
    except Exception:
        logger.exception("push_to_client_failed", extra={"message_type": type(message).__name__})


async def _periodic_state_sync(
    ws: WebSocket,
    session_id: str,
    session_manager: SessionManager,
) -> None:
    try:
        while True:
            await asyncio.sleep(5)
            ctx = session_manager.get_session(session_id)
            if ctx is None:
                break
            msg = StateUpdateMessage(
                meeting=ctx.state.meeting,
                agenda=ctx.state.agenda,
                hints=ctx.state.get_active_hints(),
                recent_transcript=ctx.state.get_window()[-5:],
            )
            await push_to_client(ws, msg)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("State sync loop failed for session %s", session_id)


def _log_session_closed(ctx: Any, connected_at: float) -> None:
    if ctx is None:
        return
    usage = ctx.orchestrator.usage
    agenda = ctx.state.agenda
    log_event(
        logger, "session_closed",
        duration_s=round(time.monotonic() - connected_at, 1),
        llm_calls=usage.calls, input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        est_cost_usd=round(usage.cost_usd, 6),
        agenda_statuses={i.id: i.status.value for i in agenda.items},
        hints_total=ctx.state.hint_count,
        hints_dismissed=ctx.state.hint_count - len(ctx.state.get_active_hints()),
    )


def _log_hint_pushed(hint: Any, source: str) -> None:
    log_event(
        logger, "hint_pushed", source=source, hint_id=hint.id,
        hint_type=hint.type.value, agenda_item_id=hint.agenda_item_id,
        confidence=round(hint.confidence, 2),
        evidence_segments=len(hint.evidence_segment_ids),
    )


def _make_hint_sink(
    ws: WebSocket,
    ctx: Any,
    session_id: str,
    session_manager: SessionManager,
) -> Any:
    """Sink for hints produced by the orchestrator's background LLM call."""

    async def _push_background_hints(hints: list[Hint]) -> None:
        if session_manager.get_session(session_id) is None:
            log_event(
                logger, "llm_result_dropped", reason="session_closed", hints=len(hints),
            )
            return
        for hint in hints:
            ctx.state.add_hint(hint)
            await push_to_client(ws, NewHintMessage(hint=hint))
            _log_hint_pushed(hint, source="llm")

    return _push_background_hints


async def _close_orchestrator(ctx: Any, wait_for_llm: bool, timeout: float) -> None:
    """End background work of a session. With ``wait_for_llm`` an in-flight call
    may still deliver its hints (bounded by ``timeout``) before everything is
    cancelled; without it the result is dropped."""
    try:
        if wait_for_llm:
            try:
                await asyncio.wait_for(ctx.orchestrator.drain(), timeout=timeout)
            except asyncio.TimeoutError:
                log_event(logger, "llm_drain_timeout", level=logging.WARNING, timeout_s=timeout)
        await ctx.orchestrator.aclose()
    except Exception:
        logger.exception("orchestrator_close_failed")


async def _handle_transcript(
    ws: WebSocket,
    data: dict[str, Any],
    ctx: Any,
    session_id: str,
) -> None:
    segment_data = data.get("segment")
    if segment_data is None:
        log_event(logger, "segment_rejected", level=logging.WARNING, reason="missing_segment_field")
        await push_to_client(
            ws,
            TranscriptErrorMessage(error="Missing 'segment' field"),
        )
        return

    try:
        segment = TranscriptSegment.model_validate(segment_data)
    except ValidationError as exc:
        log_event(
            logger, "segment_rejected", level=logging.WARNING,
            reason="validation_error", error_count=exc.error_count(),
            fields=sorted({str(e["loc"][0]) for e in exc.errors() if e.get("loc")}),
        )
        await push_to_client(
            ws,
            TranscriptErrorMessage(
                error=f"Invalid segment: {exc}",
                segment_id=segment_data.get("id") if isinstance(segment_data, dict) else None,
            ),
        )
        return

    segment.text = sanitize_transcript_text(segment.text)

    started = time.monotonic()
    try:
        result = await ctx.orchestrator.process_segment(segment, ctx.state)
    except Exception:
        logger.exception("segment_processing_failed", extra={"segment_id": segment.id})
        await push_to_client(
            ws,
            TranscriptErrorMessage(
                error="Internal processing error",
                segment_id=segment.id,
            ),
        )
        return

    await push_to_client(ws, NewTranscriptMessage(segment=segment))

    if result.agenda_delta and (
        result.agenda_delta.status_changes
        or result.agenda_delta.new_active_item_id is not None
    ):
        await push_to_client(ws, AgendaUpdateMessage(agenda=ctx.state.agenda))

    # LLM hints are not in ``result``: they arrive later through the hint sink.
    for warning in result.time_warnings:
        ctx.state.add_hint(warning)
        await push_to_client(ws, NewHintMessage(hint=warning))
        _log_hint_pushed(warning, source="time_warning")

    log_event(
        logger, "segment_processed",
        level=logging.INFO if segment.is_final else logging.DEBUG,
        segment_id=segment.id, final=segment.is_final,
        words=len(segment.text.split()),
        duration_ms=round((time.monotonic() - started) * 1000),
        llm_triggered=result.llm_triggered, time_warnings=len(result.time_warnings),
    )


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    session_manager = _get_session_manager()
    config = _get_config()

    await ws.accept()

    session_id: str | None = None
    ctx: Any = None
    sync_task: asyncio.Task[None] | None = None
    connected_at = time.monotonic()

    try:
        raw = await ws.receive_json()
        try:
            connect_msg = ConnectMessage.model_validate(raw)
        except ValidationError as exc:
            log_event(
                logger, "connect_rejected", level=logging.WARNING,
                error_count=exc.error_count(),
                fields=sorted({str(e["loc"][0]) for e in exc.errors() if e.get("loc")}),
            )
            await ws.send_json({"error": str(exc)})
            await ws.close(code=1008, reason="Invalid CONNECT message")
            return

        session_id = str(uuid4())
        ctx = session_manager.create_session(
            session_id=session_id,
            meeting_id=connect_msg.meeting_id,
            agenda_items=connect_msg.agenda_items,
            websocket=ws,
            config=config,
            api_key_override=connect_msg.api_key,
        )
        ctx.state.meeting.title = connect_msg.title
        ctx.state.meeting.participants = connect_msg.participants

        # Set before any task is created: asyncio tasks copy the context at
        # creation, so background LLM/flush tasks log with this session id.
        set_session_context(session_id, connect_msg.meeting_id)
        ctx.orchestrator.set_hint_sink(
            _make_hint_sink(ws, ctx, session_id, session_manager)
        )
        connected_at = time.monotonic()
        log_event(
            logger, "session_started",
            agenda_items=len(connect_msg.agenda_items),
            participants=len(connect_msg.participants),
            api_key_from_client=bool(connect_msg.api_key),
            model=config.anthropic_model,
            active_sessions=session_manager.active_count,
        )

        ack = SessionAckMessage(session_id=session_id)
        await push_to_client(ws, ack)

        sync_task = asyncio.create_task(
            _periodic_state_sync(ws, session_id, session_manager)
        )

        while True:
            raw_message = await ws.receive()

            if raw_message.get("type") == "websocket.disconnect":
                break

            if "text" in raw_message:
                data: dict[str, Any] = json.loads(raw_message["text"])
                msg_type = data.get("type")

                if msg_type == "AUDIO_START":
                    ctx.state.meeting.capture_state = CaptureState.CAPTURING
                    log_event(logger, "capture_started")

                elif msg_type == "AUDIO_STOP":
                    ctx.state.meeting.capture_state = CaptureState.STOPPED
                    log_event(logger, "capture_stopped")

                    # Let a call in flight deliver its hints, then stop background work.
                    await _close_orchestrator(
                        ctx, wait_for_llm=True, timeout=config.llm_timeout_seconds + 1.0
                    )

                    summary_text = await ctx.orchestrator.generate_summary(ctx.state)

                    agenda = ctx.state.agenda
                    covered = [
                        item.id
                        for item in agenda.items
                        if item.status.value == "covered"
                    ]
                    missed = [
                        item.id
                        for item in agenda.items
                        if item.status.value in ("pending", "skipped")
                    ]
                    stats = compute_meeting_stats(ctx.state)
                    agent = ctx.orchestrator.summary_agent
                    will_call_llm = agent.skip_reason(ctx.state) is None
                    log_event(
                        logger, "meeting_stats",
                        duration_s=stats.duration_seconds, final_segments=stats.final_segments,
                        total_words=stats.total_words, speakers=len(stats.speakers),
                        llm_report=will_call_llm,
                    )
                    if will_call_llm:
                        # Statistics are instant; show them while the report is written.
                        await push_to_client(
                            ws,
                            MeetingSummaryMessage(
                                summary=summary_text, covered_items=covered,
                                missed_items=missed, stats=stats, pending=True,
                            ),
                        )
                    report = await agent.summarize(ctx.state)
                    summary_msg = MeetingSummaryMessage(
                        summary=summary_text,
                        covered_items=covered,
                        missed_items=missed,
                        stats=stats,
                        report=report,
                    )
                    await push_to_client(ws, summary_msg)
                    _log_session_closed(ctx, connected_at)
                    session_manager.remove_session(session_id)
                    session_id = None
                    break

                elif msg_type == "DISMISS_HINT":
                    hint_id = data.get("hint_id", "")
                    ctx.state.dismiss_hint(hint_id)
                    log_event(logger, "hint_dismissed", hint_id=hint_id)

                elif msg_type == "TRANSCRIPT":
                    await _handle_transcript(ws, data, ctx, session_id)

                else:
                    log_event(
                        logger, "unknown_message_type", level=logging.WARNING,
                        message_type=str(msg_type)[:40],
                    )

            elif "bytes" in raw_message:
                chunk: bytes = raw_message["bytes"]
                log_event(logger, "audio_chunk", level=logging.DEBUG, bytes=len(chunk))

    except WebSocketDisconnect:
        log_event(logger, "client_disconnected")
    except Exception:
        logger.exception("websocket_error")
        try:
            await ws.close(code=1011, reason="Internal error")
        except Exception:
            pass
    finally:
        # Synchronous cleanup first: this handler may itself be cancelled (server
        # shutdown), and then the awaits below do not complete.
        if sync_task is not None:
            sync_task.cancel()
        if session_id is not None:
            _log_session_closed(session_manager.get_session(session_id), connected_at)
            session_manager.remove_session(session_id)
        try:
            if ctx is not None:
                # Client gone or error: drop any in-flight result. aclose() is
                # idempotent and cancels its tasks before its first await.
                await _close_orchestrator(ctx, wait_for_llm=False, timeout=0.0)
            if sync_task is not None:
                try:
                    await sync_task
                except asyncio.CancelledError:
                    pass
        finally:
            set_session_context(None)
