from __future__ import annotations

from enum import Enum

from .base import CamelModel


class MeetingStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ENDED = "ended"


class CaptureState(str, Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    PAUSED = "paused"
    STOPPED = "stopped"


class MeetingInfo(CamelModel):
    id: str
    title: str
    start_time: float
    participants: list[str] = []
    status: MeetingStatus = MeetingStatus.DISCONNECTED
    capture_state: CaptureState = CaptureState.IDLE
