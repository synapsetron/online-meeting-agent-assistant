from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    host: str = "0.0.0.0"
    port: int = 8000

    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
    )

    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))

    # Token-cost controls: small window, rare calls, hard per-session cap.
    transcript_window_size: int = 8
    llm_debounce_seconds: float = 45.0  # min seconds between hint calls
    llm_min_new_words: int = 50  # skip the call until this much new speech arrived
    # Caps as a budget: the cost cap is the real hard stop, the call cap is a
    # runaway guard. At ~$0.0002 per call (measured on one session, not a
    # guarantee) a one-hour meeting at one call per 45 s is ~80 calls ≈ $0.015.
    llm_max_calls_per_session: int = 200
    llm_max_session_cost_usd: float = 0.05  # hard stop on estimated LLM spend
    # Idle flush: analyse pending speech once nobody has spoken for this long
    # (0 disables). Still subject to the minimum interval and both caps.
    llm_flush_idle_seconds: float = 20.0
    llm_flush_min_words: int = 12  # do not flush less pending speech than this
    llm_max_output_tokens: int = 250
    summary_interval: int = 10_000  # final segments between rolling-summary updates (effectively off)
    llm_timeout_seconds: float = 10.0

    # End-of-meeting report: one LLM call per meeting (see server/agents/summary_agent.py).
    summary_llm_enabled: bool = True
    summary_min_words: int = 30  # below this there is nothing to summarise
    summary_max_input_chars: int = 40_000  # transcript budget; longer input is cut in the middle
    summary_max_output_tokens: int = 700
    summary_timeout_seconds: float = 20.0
    max_concurrent_sessions: int = 50

    @classmethod
    def from_env(cls) -> Config:
        return cls()
