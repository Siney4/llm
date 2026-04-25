"""Anthropic Claude provider (streaming messages API)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from anthropic import AnthropicError, AsyncAnthropic

from bot.providers.base import ChatMessage, LLMProvider, ProviderError

log = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str, models: list[str]) -> None:
        if not api_key:
            raise ValueError("Anthropic API key is required")
        if not models:
            raise ValueError("At least one Anthropic model must be configured")
        self._client = AsyncAnthropic(api_key=api_key)
        self.models = tuple(models)

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        max_output_tokens: int,
    ) -> AsyncIterator[str]:
        if model not in self.models:
            raise ProviderError(f"Model {model!r} is not configured for Anthropic")

        # Anthropic takes the system prompt as a separate kwarg, not in messages.
        system_parts = [m.content for m in messages if m.role == "system"]
        system_prompt = "\n\n".join(system_parts) if system_parts else None

        payload = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in {"user", "assistant"}
        ]

        try:
            kwargs: dict[str, object] = {
                "model": model,
                "messages": payload,
                "max_tokens": max_output_tokens,
            }
            if system_prompt is not None:
                kwargs["system"] = system_prompt

            async with self._client.messages.stream(**kwargs) as stream:  # type: ignore[arg-type]
                async for text in stream.text_stream:
                    if text:
                        yield text
        except AnthropicError as e:
            log.exception("Anthropic stream failed")
            raise ProviderError(f"Anthropic error: {e}") from e
