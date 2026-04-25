"""Plain message handler: forward to the selected LLM and stream back."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from html import escape

from aiogram import Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message

from bot.config import Settings
from bot.db import Repo
from bot.providers import ChatMessage, ProviderError, ProviderRegistry

log = logging.getLogger(__name__)
router = Router(name="messages")

# Telegram hard limit on a single message is 4096 characters.
TG_MAX_MESSAGE_LEN = 4000
# Minimum seconds between successive edits of the same message (rate-limit friendly).
EDIT_MIN_INTERVAL = 1.0
# Keep a typing indicator alive every N seconds while generating.
TYPING_INTERVAL = 4.0


@router.message()
async def handle_message(
    message: Message,
    repo: Repo,
    registry: ProviderRegistry,
    settings: Settings,
) -> None:
    if settings.allowed_user_ids:
        uid = message.from_user.id if message.from_user else None
        if uid is None or uid not in settings.allowed_user_ids:
            return

    if message.from_user is None or not message.text:
        return

    user_id = message.from_user.id
    user_row = await repo.get_user(user_id)
    if user_row is None or not registry.is_valid_pair(user_row.provider, user_row.model):
        provider, model = registry.pick_default()
        await repo.upsert_user(user_id, provider, model)
    else:
        provider, model = user_row.provider, user_row.model

    await repo.append_message(user_id, "user", message.text)

    history = await repo.get_history(user_id, settings.max_history_messages)
    messages: list[ChatMessage] = [ChatMessage(role="system", content=settings.system_prompt)]
    messages.extend(history)

    provider_obj = registry.get(provider)

    # Acknowledge with typing status right away.
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)  # type: ignore[union-attr]

    placeholder = await message.answer("…")

    typing_task = asyncio.create_task(_keep_typing(message))

    accumulated = ""
    last_edit_ts = 0.0
    last_rendered: str | None = None

    try:
        async for piece in provider_obj.stream_chat(
            model=model,
            messages=messages,
            max_output_tokens=settings.max_output_tokens,
        ):
            accumulated += piece
            now = time.monotonic()
            if now - last_edit_ts < EDIT_MIN_INTERVAL:
                continue
            rendered = _truncate_for_tg(accumulated)
            if rendered != last_rendered:
                try:
                    await placeholder.edit_text(escape(rendered) + " ▍")
                    last_rendered = rendered
                    last_edit_ts = now
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except TelegramBadRequest:
                    # Most common cause: message is not modified; ignore.
                    last_edit_ts = now

        final_text = accumulated.strip() or "(empty response)"
        await _finalize(placeholder, final_text)
        await repo.append_message(user_id, "assistant", final_text)

    except ProviderError as e:
        log.warning("Provider error for user=%s: %s", user_id, e)
        await _finalize(placeholder, f"⚠️ {escape(str(e))}")
    except Exception as e:  # noqa: BLE001
        log.exception("Unexpected error while streaming reply for user=%s", user_id)
        await _finalize(placeholder, f"⚠️ Internal error: {escape(str(e))}")
    finally:
        typing_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await typing_task


async def _keep_typing(message: Message) -> None:
    """Send the 'typing' chat action every few seconds until cancelled."""
    try:
        while True:
            with contextlib.suppress(Exception):
                await message.bot.send_chat_action(  # type: ignore[union-attr]
                    message.chat.id, ChatAction.TYPING
                )
            await asyncio.sleep(TYPING_INTERVAL)
    except asyncio.CancelledError:
        return


def _truncate_for_tg(text: str) -> str:
    if len(text) <= TG_MAX_MESSAGE_LEN:
        return text
    # Keep the tail of a long response so the user sees the latest tokens.
    suffix = text[-TG_MAX_MESSAGE_LEN:]
    return "… " + suffix


async def _finalize(placeholder: Message, text: str) -> None:
    """Send the final text, splitting into multiple messages if needed."""
    chunks = _split_for_tg(text)
    first = chunks[0]
    try:
        await placeholder.edit_text(escape(first))
    except TelegramBadRequest:
        # Unchanged content or similar — fall back to a fresh message.
        await placeholder.answer(escape(first))
    for extra in chunks[1:]:
        await placeholder.answer(escape(extra))


def _split_for_tg(text: str) -> list[str]:
    if len(text) <= TG_MAX_MESSAGE_LEN:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > TG_MAX_MESSAGE_LEN:
        # Try to break on a newline near the limit to keep chunks readable.
        cut = remaining.rfind("\n", 0, TG_MAX_MESSAGE_LEN)
        if cut < TG_MAX_MESSAGE_LEN // 2:
            cut = TG_MAX_MESSAGE_LEN
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks
