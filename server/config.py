from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    host: str = "0.0.0.0"
    port: int = 8000

    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = "claude-sonnet-4-20250514"

    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))

    transcript_window_size: int = 20
    llm_debounce_seconds: float = 2.5
    llm_timeout_seconds: float = 10.0
    max_concurrent_sessions: int = 50

    @classmethod
    def from_env(cls) -> Config:
        return cls()
