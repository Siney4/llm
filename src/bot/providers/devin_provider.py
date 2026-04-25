"""Devin API provider.

Wraps Devin's v1 sessions API as a chat-style streaming provider:

* A user message either resumes the user's existing active session
  (via POST /v1/sessions/{id}/message) or creates a new one (POST /v1/sessions).
* The provider polls GET /v1/sessions/{id} every `poll_interval` seconds,
  emitting any new messages produced by Devin as stream deltas.
* When the session reports `status_enum` ∈ {finished, expired, blocked},
  the provider stops polling.

Because Devin does NOT currently expose a "model" parameter in the public API,
the `models` list here is purely a cosmetic label set (e.g. "Agent", "Fast Mode").
The actual underlying LLM is whatever the Devin organization is configured to use.
See: https://docs.devin.ai/api-reference/v1/sessions/create-a-new-devin-session
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from bot.providers.base import ChatMessage, LLMProvider, ProviderContext, ProviderError

log = logging.getLogger(__name__)

# Devin session states that mean "no more messages are coming".
TERMINAL_STATES = {"finished", "expired"}
# Devin session states that mean "temporarily idle; user needs to send another message".
PAUSED_STATES = {"blocked", "suspend_requested", "suspend_requested_frontend"}

# Event types that are user-visible "chat" output.
VISIBLE_MESSAGE_TYPES = {"devin_message", "agent_message", "message"}

# Session-state keys persisted in ProviderStateStore.
STATE_KEY_SESSION_ID = "session_id"
STATE_KEY_SEEN_EVENTS = "seen_event_ids"


class DevinProvider(LLMProvider):
    name = "devin"

    def __init__(
        self,
        *,
        api_key: str,
        models: list[str],
        base_url: str = "https://api.devin.ai",
        poll_interval: float = 3.0,
        max_acu_limit: int | None = 1,
        advanced_mode: str | None = None,
        request_timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("Devin API key is required")
        if not models:
            raise ValueError("At least one Devin model label must be configured")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._poll_interval = poll_interval
        self._max_acu_limit = max_acu_limit
        self._advanced_mode = advanced_mode
        self._timeout = request_timeout
        self.models = tuple(models)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        max_output_tokens: int,
        context: ProviderContext,
    ) -> AsyncIterator[str]:
        _ = model  # Devin API does not accept a model parameter; label is cosmetic.
        _ = max_output_tokens  # Devin caps output via ACU limits, not token limits.

        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        if last_user is None:
            raise ProviderError("Devin provider requires at least one user message")
        prompt = last_user.content

        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers(),
            timeout=self._timeout,
        ) as client:
            session_id, seen_events = await self._resume_or_create(client, context, prompt)
            yield f"▶️ Devin session {session_id} started…\n"

            # Keep the first poll quick so the user sees early output.
            await asyncio.sleep(min(self._poll_interval, 2.0))

            try:
                async for piece in self._poll_loop(client, session_id, seen_events, context):
                    yield piece
            finally:
                await context.state.set(
                    STATE_KEY_SEEN_EVENTS,
                    json.dumps(sorted(seen_events)),
                )

    async def _resume_or_create(
        self,
        client: httpx.AsyncClient,
        context: ProviderContext,
        prompt: str,
    ) -> tuple[str, set[str]]:
        existing = await context.state.get(STATE_KEY_SESSION_ID)
        if existing:
            info = await self._get_session(client, existing)
            status = info.get("status_enum")
            if status not in TERMINAL_STATES:
                seen = self._load_seen(await context.state.get(STATE_KEY_SEEN_EVENTS))
                if status in PAUSED_STATES or status == "working":
                    await self._post_message(client, existing, prompt)
                return existing, seen

        # Start fresh.
        session_id = await self._create_session(client, prompt)
        await context.state.set(STATE_KEY_SESSION_ID, session_id)
        await context.state.set(STATE_KEY_SEEN_EVENTS, json.dumps([]))
        return session_id, set()

    async def _create_session(self, client: httpx.AsyncClient, prompt: str) -> str:
        body: dict[str, Any] = {"prompt": prompt}
        if self._max_acu_limit is not None:
            body["max_acu_limit"] = self._max_acu_limit
        try:
            resp = await client.post("/v1/sessions", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"Devin create_session failed: {e}") from e
        data = resp.json()
        session_id = data.get("session_id")
        if not session_id:
            raise ProviderError(f"Devin create_session returned no session_id: {data!r}")
        log.info("Devin session created: %s", session_id)
        return str(session_id)

    async def _post_message(
        self,
        client: httpx.AsyncClient,
        session_id: str,
        message: str,
    ) -> None:
        try:
            resp = await client.post(
                f"/v1/sessions/{session_id}/message",
                json={"message": message},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"Devin send_message failed: {e}") from e

    async def _get_session(
        self,
        client: httpx.AsyncClient,
        session_id: str,
    ) -> dict[str, Any]:
        try:
            resp = await client.get(f"/v1/sessions/{session_id}")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"Devin get_session failed: {e}") from e
        data = resp.json()
        if not isinstance(data, dict):
            raise ProviderError(f"Devin get_session returned non-dict: {data!r}")
        return data

    @staticmethod
    def _load_seen(raw: str | None) -> set[str]:
        if not raw:
            return set()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return set()
        if isinstance(parsed, list):
            return {str(x) for x in parsed}
        return set()

    async def _poll_loop(
        self,
        client: httpx.AsyncClient,
        session_id: str,
        seen_events: set[str],
        context: ProviderContext,
    ) -> AsyncIterator[str]:
        while True:
            info = await self._get_session(client, session_id)
            messages = info.get("messages") or []

            for msg in messages:
                event_id = str(msg.get("event_id", ""))
                if not event_id or event_id in seen_events:
                    continue
                seen_events.add(event_id)

                if msg.get("origin") == "user":
                    continue
                msg_type = str(msg.get("type", ""))
                text = str(msg.get("message", "")).strip()
                if not text:
                    continue
                if msg_type and msg_type not in VISIBLE_MESSAGE_TYPES:
                    # Render internal events (shell_command, file_edit, …) compactly.
                    yield f"<i>[{msg_type}]</i>\n"
                    continue
                yield text + "\n\n"

            status = info.get("status_enum")
            if status in TERMINAL_STATES:
                yield f"\n— session {status} —"
                await context.state.delete(STATE_KEY_SESSION_ID)
                return
            if status in PAUSED_STATES:
                yield "\n⏸️ Devin is waiting for input. Send another message to continue."
                # Persist seen_events so the next call resumes cleanly.
                await context.state.set(
                    STATE_KEY_SEEN_EVENTS,
                    json.dumps(sorted(seen_events)),
                )
                return

            await asyncio.sleep(self._poll_interval)
