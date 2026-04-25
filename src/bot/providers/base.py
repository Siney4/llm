"""Shared provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class ProviderError(RuntimeError):
    """Raised when an upstream LLM provider fails."""


class LLMProvider(ABC):
    """Abstract async chat provider.

    Implementations must stream the response as plain-text deltas.
    """

    name: str
    models: tuple[str, ...]

    @abstractmethod
    def stream_chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        max_output_tokens: int,
    ) -> AsyncIterator[str]:
        """Yield incremental text chunks as they arrive from the provider."""
