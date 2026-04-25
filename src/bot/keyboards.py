"""Inline keyboard builders."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.providers import ProviderRegistry


def provider_keyboard(registry: ProviderRegistry) -> InlineKeyboardMarkup:
    """Top-level keyboard: pick a provider."""
    rows: list[list[InlineKeyboardButton]] = []
    for name in registry.available():
        label = _pretty_provider(name)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"pick_provider:{name}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_keyboard(registry: ProviderRegistry, provider: str) -> InlineKeyboardMarkup:
    """Second-level keyboard: pick a model for a provider."""
    provider_obj = registry.get(provider)
    rows: list[list[InlineKeyboardButton]] = []
    for model in provider_obj.models:
        rows.append(
            [
                InlineKeyboardButton(
                    text=model,
                    callback_data=f"pick_model:{provider}:{model}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="« Back", callback_data="pick_provider_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pretty_provider(name: str) -> str:
    return {
        "openai": "🟢 OpenAI (ChatGPT)",
        "anthropic": "🟣 Anthropic (Claude)",
        "devin": "🤖 Devin (coding agent)",
    }.get(name, name)
