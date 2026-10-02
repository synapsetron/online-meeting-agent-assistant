from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class AgendaItemStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COVERED = "covered"
    DEFERRED = "deferred"
    SKIPPED = "skipped"


class AgendaItem(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: AgendaItemStatus = AgendaItemStatus.PENDING
    estimated_minutes: float | None = None
    elapsed_seconds: float = 0.0
    evidence: list[str] = []
    order: int


class AgendaState(BaseModel):
    items: list[AgendaItem]
    active_item_id: str | None = None
    start_time: float = 0.0
    total_elapsed_seconds: float = 0.0
