"""Shared provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class ProviderError(RuntimeError):
    """Raised when an upstream LLM provider fails."""


class ProviderStateStore(Protocol):
    """Key-value persistent store scoped to (user_id, provider)."""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str) -> None: ...
    async def delete(self, key: str) -> None: ...


@dataclass(slots=True)
class ProviderContext:
    """Per-call context passed into provider.stream_chat."""

    user_id: int
    state: ProviderStateStore


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
        context: ProviderContext,
    ) -> AsyncIterator[str]:
        """Yield incremental text chunks as they arrive from the provider."""
