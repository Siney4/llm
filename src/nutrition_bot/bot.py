"""Bot entrypoint: wires config, storage, LLM provider and the aiogram dispatcher."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from nutrition_bot.config import Settings, load_settings
from nutrition_bot.handlers import build_router
from nutrition_bot.llm import MealGenerator
from nutrition_bot.storage import Storage

log = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Анкета и план питания"),
            BotCommand(command="plan", description="Текущий план"),
            BotCommand(command="meal", description="Сгенерировать блюдо"),
            BotCommand(command="notes", description="Ограничения по еде"),
            BotCommand(command="reset", description="Сбросить профиль"),
        ]
    )


def build_llm(settings: Settings) -> MealGenerator:
    return MealGenerator(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_s=settings.llm_timeout_s,
    )


async def run() -> None:
    settings = load_settings()
    _setup_logging(settings.log_level)

    storage = Storage(settings.db_path)
    await storage.open()
    llm = build_llm(settings)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(build_router())

    # Pass shared deps to handlers via aiogram's DI.
    dp.workflow_data["storage"] = storage
    dp.workflow_data["settings"] = settings
    dp.workflow_data["llm"] = llm

    await _set_commands(bot)
    log.info(
        "Starting nutrition-bot. LLM=%s @ %s, db=%s",
        settings.openai_model,
        settings.openai_base_url,
        settings.db_path,
    )
    try:
        await dp.start_polling(bot)
    finally:
        await llm.close()
        await storage.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
