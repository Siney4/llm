"""Bot entrypoint: wires config, DB, providers and aiogram dispatcher."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import load_settings
from bot.db import open_repo
from bot.handlers import build_router
from bot.providers import build_registry

log = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Intro and current model"),
            BotCommand(command="help", description="Show help"),
            BotCommand(command="model", description="Pick provider and model"),
            BotCommand(command="models", description="List available models"),
            BotCommand(command="reset", description="Clear conversation history"),
        ]
    )


async def run() -> None:
    settings = load_settings()
    _setup_logging(settings.log_level)

    registry = build_registry(settings)
    log.info(
        "Providers configured: %s (default=%s)",
        ", ".join(registry.available()),
        registry.default_provider,
    )

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(build_router())

    async with open_repo(settings.db_path) as repo:
        await _set_commands(bot)
        log.info("Starting polling…")
        try:
            await dp.start_polling(
                bot,
                repo=repo,
                registry=registry,
                settings=settings,
            )
        finally:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
