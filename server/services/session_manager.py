from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from server.models import AgendaItem
from server.core.state_store import MeetingStateStore

if TYPE_CHECKING:
    from server.agents.orchestrator import Orchestrator
    from server.config import Config


@dataclass
class SessionContext:
    session_id: str
    meeting_id: str
    state: MeetingStateStore
    orchestrator: Orchestrator
    created_at: float
    websocket: Any


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}

    def create_session(
        self,
        session_id: str,
        meeting_id: str,
        agenda_items: list[AgendaItem],
        websocket: Any,
        config: Config,
        api_key_override: str | None = None,
    ) -> SessionContext:
        from server.agents.orchestrator import Orchestrator

        state = MeetingStateStore(
            meeting_id=meeting_id,
            agenda_items=agenda_items,
            window_size=config.transcript_window_size,
        )
        orchestrator = Orchestrator(config=config, api_key_override=api_key_override)
        ctx = SessionContext(
            session_id=session_id,
            meeting_id=meeting_id,
            state=state,
            orchestrator=orchestrator,
            created_at=time.time(),
            websocket=websocket,
        )
        self._sessions[session_id] = ctx
        return ctx

    def get_session(self, session_id: str) -> SessionContext | None:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return len(self._sessions)
