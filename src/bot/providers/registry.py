"""Registry that holds configured providers."""

from __future__ import annotations

from dataclasses import dataclass

from bot.config import Settings
from bot.providers.anthropic_provider import AnthropicProvider
from bot.providers.base import LLMProvider
from bot.providers.devin_provider import DevinProvider
from bot.providers.openai_provider import OpenAIProvider


@dataclass(slots=True)
class ProviderRegistry:
    providers: dict[str, LLMProvider]
    default_provider: str
    default_model_by_provider: dict[str, str]

    def get(self, name: str) -> LLMProvider:
        if name not in self.providers:
            raise KeyError(f"Unknown provider: {name}")
        return self.providers[name]

    def available(self) -> list[str]:
        return sorted(self.providers.keys())

    def is_valid_pair(self, provider: str, model: str) -> bool:
        return provider in self.providers and model in self.providers[provider].models

    def pick_default(self) -> tuple[str, str]:
        """Pick a (provider, model) pair. Prefer the configured default, else the first available."""
        if self.default_provider in self.providers:
            provider = self.default_provider
        else:
            provider = next(iter(sorted(self.providers.keys())))
        model = self.default_model_by_provider[provider]
        return provider, model


def build_registry(settings: Settings) -> ProviderRegistry:
    providers: dict[str, LLMProvider] = {}
    defaults: dict[str, str] = {}

    if settings.has_openai():
        providers["openai"] = OpenAIProvider(
            api_key=settings.openai_api_key,
            models=settings.openai_models,
        )
        defaults["openai"] = settings.openai_models[0]

    if settings.has_anthropic():
        providers["anthropic"] = AnthropicProvider(
            api_key=settings.anthropic_api_key,
            models=settings.anthropic_models,
        )
        defaults["anthropic"] = settings.anthropic_models[0]

    if settings.has_devin():
        providers["devin"] = DevinProvider(
            api_key=settings.devin_api_key,
            models=settings.devin_models,
            base_url=settings.devin_base_url,
            poll_interval=settings.devin_poll_interval,
            max_acu_limit=settings.devin_max_acu_limit,
        )
        defaults["devin"] = settings.devin_models[0]

    if not providers:
        raise RuntimeError(
            "No providers configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY or "
            "DEVIN_API_KEY in .env."
        )

    return ProviderRegistry(
        providers=providers,
        default_provider=settings.default_provider,
        default_model_by_provider=defaults,
    )
