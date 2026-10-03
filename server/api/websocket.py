from __future__ import annotations

import asyncio
import json
import logging
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
    NewTranscriptMessage,
    SessionAckMessage,
    StateUpdateMessage,
    TranscriptErrorMessage,
    TranscriptSegment,
)
from server.core.validation import sanitize_transcript_text
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
    except Exception:
        logger.exception("Failed to push message to client")


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


async def _handle_transcript(
    ws: WebSocket,
    data: dict[str, Any],
    ctx: Any,
    session_id: str,
) -> None:
    segment_data = data.get("segment")
    if segment_data is None:
        await push_to_client(
            ws,
            TranscriptErrorMessage(error="Missing 'segment' field"),
        )
        return

    try:
        segment = TranscriptSegment.model_validate(segment_data)
    except ValidationError as exc:
        await push_to_client(
            ws,
            TranscriptErrorMessage(
                error=f"Invalid segment: {exc}",
                segment_id=segment_data.get("id") if isinstance(segment_data, dict) else None,
            ),
        )
        return

    segment.text = sanitize_transcript_text(segment.text)

    try:
        result = await ctx.orchestrator.process_segment(segment, ctx.state)
    except Exception:
        logger.exception(
            "Orchestrator error processing segment %s in session %s",
            segment.id,
            session_id,
        )
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

    for hint in result.hints:
        ctx.state.add_hint(hint)
        await push_to_client(ws, NewHintMessage(hint=hint))

    for warning in result.time_warnings:
        ctx.state.add_hint(warning)
        await push_to_client(ws, NewHintMessage(hint=warning))

    logger.debug(
        "Processed segment %s (final=%s) in session %s: "
        "%d hints, %d time warnings",
        segment.id,
        segment.is_final,
        session_id,
        len(result.hints),
        len(result.time_warnings),
    )


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    session_manager = _get_session_manager()
    config = _get_config()

    await ws.accept()

    session_id: str | None = None
    sync_task: asyncio.Task[None] | None = None

    try:
        raw = await ws.receive_json()
        try:
            connect_msg = ConnectMessage.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Invalid CONNECT message: %s", exc)
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

        logger.info(
            "Session %s created for meeting %s",
            session_id,
            connect_msg.meeting_id,
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
                    logger.info("Capture started for session %s", session_id)

                elif msg_type == "AUDIO_STOP":
                    ctx.state.meeting.capture_state = CaptureState.STOPPED
                    logger.info("Capture stopped for session %s", session_id)

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
                    summary_msg = MeetingSummaryMessage(
                        summary=summary_text,
                        covered_items=covered,
                        missed_items=missed,
                    )
                    await push_to_client(ws, summary_msg)
                    session_manager.remove_session(session_id)
                    session_id = None
                    break

                elif msg_type == "DISMISS_HINT":
                    hint_id = data.get("hint_id", "")
                    ctx.state.dismiss_hint(hint_id)
                    logger.debug(
                        "Hint %s dismissed in session %s", hint_id, session_id
                    )

                elif msg_type == "TRANSCRIPT":
                    await _handle_transcript(ws, data, ctx, session_id)

                else:
                    logger.warning(
                        "Unknown message type %r in session %s",
                        msg_type,
                        session_id,
                    )

            elif "bytes" in raw_message:
                chunk: bytes = raw_message["bytes"]
                logger.debug(
                    "Audio chunk received: %d bytes (session %s)",
                    len(chunk),
                    session_id,
                )

    except WebSocketDisconnect:
        logger.info("Client disconnected (session %s)", session_id)
    except Exception:
        logger.exception("WebSocket error (session %s)", session_id)
        try:
            await ws.close(code=1011, reason="Internal error")
        except Exception:
            pass
    finally:
        if sync_task is not None:
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass
        if session_id is not None:
            session_manager.remove_session(session_id)
            logger.info("Session %s cleaned up", session_id)
