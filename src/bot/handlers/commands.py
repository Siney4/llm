"""Command handlers: /start, /help, /model, /reset, /models, /stats."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db import Repo
from bot.keyboards import model_keyboard, provider_keyboard
from bot.providers import ProviderRegistry

router = Router(name="commands")


HELP_TEXT = (
    "🤖 <b>LLM Aggregator</b>\n\n"
    "Just send me a message — I'll forward it to the selected model and stream the answer back.\n\n"
    "<b>Commands</b>\n"
    "/start — intro\n"
    "/help — this message\n"
    "/model — choose provider and model\n"
    "/models — list all available models\n"
    "/reset — clear conversation history\n"
    "/stats — bot usage stats (admins)"
)


def _access_denied(message: Message, settings: Settings) -> bool:
    if not settings.allowed_user_ids:
        return False
    uid = message.from_user.id if message.from_user else None
    return uid is None or uid not in settings.allowed_user_ids


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    repo: Repo,
    registry: ProviderRegistry,
    settings: Settings,
) -> None:
    if _access_denied(message, settings):
        await message.answer("Access to this bot is restricted.")
        return

    assert message.from_user is not None
    existing = await repo.get_user(message.from_user.id)
    if existing is None or not registry.is_valid_pair(existing.provider, existing.model):
        provider, model = registry.pick_default()
        await repo.upsert_user(message.from_user.id, provider, model)
    else:
        provider, model = existing.provider, existing.model

    await message.answer(
        f"Hi! I aggregate OpenAI (ChatGPT) and Anthropic (Claude).\n\n"
        f"Current model: <b>{provider}</b> / <code>{model}</code>\n\n"
        f"Use /model to change it, or just send a message.",
    )


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    if _access_denied(message, settings):
        return
    await message.answer(HELP_TEXT)


@router.message(Command("models"))
async def cmd_models(message: Message, registry: ProviderRegistry, settings: Settings) -> None:
    if _access_denied(message, settings):
        return
    lines = ["<b>Available models</b>\n"]
    for provider_name in registry.available():
        provider = registry.get(provider_name)
        lines.append(f"• <b>{provider_name}</b>: {', '.join(provider.models)}")
    await message.answer("\n".join(lines))


@router.message(Command("model"))
async def cmd_model(message: Message, registry: ProviderRegistry, settings: Settings) -> None:
    if _access_denied(message, settings):
        return
    await message.answer(
        "Pick a provider:",
        reply_markup=provider_keyboard(registry),
    )


@router.message(Command("reset"))
async def cmd_reset(message: Message, repo: Repo, settings: Settings) -> None:
    if _access_denied(message, settings):
        return
    assert message.from_user is not None
    await repo.reset(message.from_user.id)
    await message.answer("Conversation history cleared.")


@router.message(Command("stats"))
async def cmd_stats(message: Message, repo: Repo, settings: Settings) -> None:
    uid = message.from_user.id if message.from_user else None
    if uid is None or uid not in settings.admin_user_ids:
        return
    users, messages = await repo.stats()
    await message.answer(f"📊 Users: <b>{users}</b>\n📝 Messages: <b>{messages}</b>")


@router.callback_query(F.data.startswith("pick_provider:"))
async def cb_pick_provider(
    query: CallbackQuery,
    registry: ProviderRegistry,
) -> None:
    assert query.data is not None
    provider = query.data.split(":", 1)[1]
    if provider not in registry.available():
        await query.answer("Unknown provider", show_alert=True)
        return
    if isinstance(query.message, Message):
        await query.message.edit_text(
            f"Pick a model for <b>{provider}</b>:",
            reply_markup=model_keyboard(registry, provider),
        )
    await query.answer()


@router.callback_query(F.data == "pick_provider_back")
async def cb_pick_provider_back(
    query: CallbackQuery,
    registry: ProviderRegistry,
) -> None:
    if isinstance(query.message, Message):
        await query.message.edit_text(
            "Pick a provider:",
            reply_markup=provider_keyboard(registry),
        )
    await query.answer()


@router.callback_query(F.data.startswith("pick_model:"))
async def cb_pick_model(
    query: CallbackQuery,
    registry: ProviderRegistry,
    repo: Repo,
) -> None:
    assert query.data is not None
    _, provider, model = query.data.split(":", 2)
    if not registry.is_valid_pair(provider, model):
        await query.answer("Unknown model", show_alert=True)
        return
    assert query.from_user is not None
    await repo.set_selection(query.from_user.id, provider, model)
    if isinstance(query.message, Message):
        await query.message.edit_text(
            f"✅ Selected <b>{provider}</b> / <code>{model}</code>\n\nSend me a message to chat.",
        )
    await query.answer("Saved")
