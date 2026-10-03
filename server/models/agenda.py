from __future__ import annotations

from enum import Enum

from .base import CamelModel


class AgendaItemStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COVERED = "covered"
    DEFERRED = "deferred"
    SKIPPED = "skipped"


class AgendaItem(CamelModel):
    id: str
    title: str
    description: str | None = None
    status: AgendaItemStatus = AgendaItemStatus.PENDING
    estimated_minutes: float | None = None
    elapsed_seconds: float = 0.0
    evidence: list[str] = []
    order: int = 0


class AgendaState(CamelModel):
    items: list[AgendaItem]
    active_item_id: str | None = None
    start_time: float = 0.0
    total_elapsed_seconds: float = 0.0
