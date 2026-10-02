from __future__ import annotations

import asyncio
import logging

try:
    import anthropic

    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        if not _HAS_ANTHROPIC:
            raise RuntimeError(
                "anthropic package is not installed — "
                "install it with: pip install anthropic"
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._timeout = timeout

    async def complete(
        self, system: str, user_content: str, max_tokens: int = 1024
    ) -> str:
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_content}],
                ),
                timeout=self._timeout,
            )
            block = response.content[0]
            if block.type == "text":
                return block.text
            return ""
        except asyncio.TimeoutError:
            logger.error("LLM request timed out after %.1fs", self._timeout)
            return ""
        except anthropic.APIError as exc:
            logger.error("LLM API error: %s", exc)
            return ""
