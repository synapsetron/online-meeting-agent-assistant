from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .agenda import AgendaItem, AgendaState
from .hint import Hint
from .meeting import CaptureState, MeetingInfo
from .transcript import TranscriptSegment


# --- Client → Server ---

class ConnectMessage(BaseModel):
    type: Literal["CONNECT"] = "CONNECT"
    meeting_id: str
    title: str
    agenda_items: list[AgendaItem]
    participants: list[str] = []


class AudioStartMessage(BaseModel):
    type: Literal["AUDIO_START"] = "AUDIO_START"
    format: str = "pcm"
    sample_rate: int = 16000


class AudioStopMessage(BaseModel):
    type: Literal["AUDIO_STOP"] = "AUDIO_STOP"


class DismissHintMessage(BaseModel):
    type: Literal["DISMISS_HINT"] = "DISMISS_HINT"
    hint_id: str


ClientMessage = Annotated[
    Union[ConnectMessage, AudioStartMessage, AudioStopMessage, DismissHintMessage],
    Field(discriminator="type"),
]


# --- Server → Client ---

class SessionAckMessage(BaseModel):
    type: Literal["SESSION_ACK"] = "SESSION_ACK"
    session_id: str


class NewTranscriptMessage(BaseModel):
    type: Literal["NEW_TRANSCRIPT"] = "NEW_TRANSCRIPT"
    segment: TranscriptSegment


class AgendaUpdateMessage(BaseModel):
    type: Literal["AGENDA_UPDATE"] = "AGENDA_UPDATE"
    agenda: AgendaState


class NewHintMessage(BaseModel):
    type: Literal["NEW_HINT"] = "NEW_HINT"
    hint: Hint


class StateUpdateMessage(BaseModel):
    type: Literal["STATE_UPDATE"] = "STATE_UPDATE"
    meeting: MeetingInfo
    agenda: AgendaState


class CaptureStateMessage(BaseModel):
    type: Literal["CAPTURE_STATE"] = "CAPTURE_STATE"
    capture_state: CaptureState


class MeetingSummaryMessage(BaseModel):
    type: Literal["MEETING_SUMMARY"] = "MEETING_SUMMARY"
    summary: str
    covered_items: list[str]
    missed_items: list[str]


ServerMessage = Annotated[
    Union[
        SessionAckMessage,
        NewTranscriptMessage,
        AgendaUpdateMessage,
        NewHintMessage,
        StateUpdateMessage,
        CaptureStateMessage,
        MeetingSummaryMessage,
    ],
    Field(discriminator="type"),
]
