"""OpenAI ChatGPT provider (streaming chat completions)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAIError

from bot.providers.base import ChatMessage, LLMProvider, ProviderContext, ProviderError

log = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, *, api_key: str, models: list[str]) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        if not models:
            raise ValueError("At least one OpenAI model must be configured")
        self._client = AsyncOpenAI(api_key=api_key)
        self.models = tuple(models)

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        max_output_tokens: int,
        context: ProviderContext,
    ) -> AsyncIterator[str]:
        _ = context  # OpenAI provider is stateless
        if model not in self.models:
            raise ProviderError(f"Model {model!r} is not configured for OpenAI")

        payload = [{"role": m.role, "content": m.content} for m in messages]

        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=payload,  # type: ignore[arg-type]
                max_completion_tokens=max_output_tokens,
                stream=True,
            )
            async for chunk in stream:  # type: ignore[union-attr]
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    yield piece
        except OpenAIError as e:
            log.exception("OpenAI stream failed")
            raise ProviderError(f"OpenAI error: {e}") from e
