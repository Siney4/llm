"""DevinProvider tests using a fake httpx transport."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from bot.providers import ChatMessage, ProviderContext
from bot.providers.devin_provider import (
    STATE_KEY_SEEN_EVENTS,
    STATE_KEY_SESSION_ID,
    DevinProvider,
)


class InMemoryState:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)


def _make_client(
    handler: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]],
) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(
        transport=transport,
        base_url="https://api.devin.ai",
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
    )


def _session_payload(
    status: str,
    messages: list[dict[str, Any]],
    session_id: str = "devin-1",
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "status": status,
        "status_enum": status,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "messages": messages,
    }


@pytest.mark.asyncio
async def test_stream_chat_creates_session_and_streams_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poll_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_calls
        if request.method == "POST" and request.url.path == "/v1/sessions":
            body = json.loads(request.content)
            assert body["prompt"] == "hello"
            assert body["max_acu_limit"] == 1
            return httpx.Response(
                200,
                json={"session_id": "devin-42", "url": "https://devin.ai/s/42"},
            )
        if request.method == "GET" and request.url.path == "/v1/sessions/devin-42":
            poll_calls += 1
            if poll_calls == 1:
                return httpx.Response(
                    200,
                    json=_session_payload(
                        "working",
                        [
                            {
                                "event_id": "e1",
                                "type": "devin_message",
                                "message": "Hi there!",
                                "timestamp": "2026-01-01T00:00:01Z",
                                "origin": "devin",
                            }
                        ],
                        session_id="devin-42",
                    ),
                )
            return httpx.Response(
                200,
                json=_session_payload(
                    "finished",
                    [
                        {
                            "event_id": "e1",
                            "type": "devin_message",
                            "message": "Hi there!",
                            "timestamp": "2026-01-01T00:00:01Z",
                            "origin": "devin",
                        },
                        {
                            "event_id": "e2",
                            "type": "devin_message",
                            "message": "All done.",
                            "timestamp": "2026-01-01T00:00:02Z",
                            "origin": "devin",
                        },
                    ],
                    session_id="devin-42",
                ),
            )
        return httpx.Response(404)

    client = _make_client(handler)

    # Patch AsyncClient so the provider uses the mock transport.
    async def fake_aenter(self: httpx.AsyncClient) -> httpx.AsyncClient:
        return client

    async def fake_aexit(self: httpx.AsyncClient, *args: object) -> None:
        return None

    monkeypatch.setattr(
        "bot.providers.devin_provider.httpx.AsyncClient",
        lambda *args, **kwargs: client,
    )
    # Don't actually close the client between enter/exit in this test.
    monkeypatch.setattr(type(client), "__aenter__", fake_aenter, raising=False)
    monkeypatch.setattr(type(client), "__aexit__", fake_aexit, raising=False)

    provider = DevinProvider(
        api_key="test",
        models=["Agent"],
        poll_interval=0.01,
        max_acu_limit=1,
    )
    state = InMemoryState()
    context = ProviderContext(user_id=1, state=state)

    pieces: list[str] = []
    async for piece in provider.stream_chat(
        model="Agent",
        messages=[ChatMessage(role="user", content="hello")],
        max_output_tokens=2048,
        context=context,
    ):
        pieces.append(piece)

    text = "".join(pieces)
    assert "devin-42" in text
    assert "Hi there!" in text
    assert "All done." in text
    assert "finished" in text
    # Session id is cleared after terminal state.
    assert state.data.get(STATE_KEY_SESSION_ID) is None
    # Seen events were persisted (non-empty).
    seen_raw = state.data.get(STATE_KEY_SEEN_EVENTS) or "[]"
    assert set(json.loads(seen_raw)) == {"e1", "e2"}
