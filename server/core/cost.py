from __future__ import annotations

from dataclasses import dataclass

# USD per million tokens: (input, output). Source: Anthropic pricing page,
# fetched 2026-10-08 (https://platform.claude.com/docs/en/about-claude/pricing).
# Haiku 5.5 rates are for prompts up to 100K tokens (our prompts are far below).
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
_CACHE_WRITE_5M = 1.25  # x base input
_CACHE_READ = 0.10  # x base input (standard multiplier; 0.05 on Sonnet/Opus 5.5)


@dataclass
class UsageMeter:
    """Accumulates billed tokens for one session and estimates their cost."""

    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    def record(self, usage: object | None) -> None:
        self.calls += 1
        if usage is None:
            return
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_write_tokens += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        self.cache_read_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)

    @property
    def cost_usd(self) -> float:
        """Estimated spend; 0.0 for models without a known price (log, don't guess)."""
        rates = PRICES_USD_PER_MTOK.get(self.model)
        if rates is None:
            return 0.0
        in_rate, out_rate = rates
        return (
            self.input_tokens * in_rate
            + self.cache_write_tokens * in_rate * _CACHE_WRITE_5M
            + self.cache_read_tokens * in_rate * _CACHE_READ
            + self.output_tokens * out_rate
        ) / 1_000_000
