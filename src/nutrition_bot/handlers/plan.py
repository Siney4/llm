"""Plan rendering: /plan and the post-onboarding plan message."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from nutrition_bot import keyboards
from nutrition_bot.config import Settings
from nutrition_bot.formatting import format_plan
from nutrition_bot.nutrition import Profile, build_plan
from nutrition_bot.storage import Storage

router = Router(name="plan")


async def send_plan(
    *,
    chat_id: int,
    bot: Bot,
    profile: Profile,
    meals_count: int,
    buffer_fraction: float,
) -> None:
    plan = build_plan(profile, meals_count=meals_count, buffer_fraction=buffer_fraction)
    text = format_plan(profile, plan)
    meal_keys = tuple(m.key for m in plan.meals)
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboards.meal_pick_kb(meal_keys, plan.buffer_kcal),
    )


@router.message(Command("plan"))
async def on_plan(message: Message, storage: Storage, settings: Settings) -> None:
    if message.from_user is None:
        return
    saved = await storage.load_profile(message.from_user.id)
    if saved is None:
        await message.answer("Сначала заполни анкету: /start")
        return
    profile, meals_count, _ = saved
    await send_plan(
        chat_id=message.chat.id,
        bot=message.bot,  # type: ignore[arg-type]
        profile=profile,
        meals_count=meals_count or 4,
        buffer_fraction=settings.buffer_fraction,
    )


@router.callback_query(F.data == "back:plan")
async def on_back(query: CallbackQuery, storage: Storage, settings: Settings) -> None:
    if query.message is None or query.from_user is None:
        return
    saved = await storage.load_profile(query.from_user.id)
    if saved is None:
        await query.answer("Профиль не найден", show_alert=True)
        return
    profile, meals_count, _ = saved
    await query.answer()
    await send_plan(
        chat_id=query.message.chat.id,
        bot=query.bot,  # type: ignore[arg-type]
        profile=profile,
        meals_count=meals_count or 4,
        buffer_fraction=settings.buffer_fraction,
    )


@router.message(Command("meals"))
async def on_meals_alias(message: Message, storage: Storage, settings: Settings) -> None:
    """Alias for /plan — quick access to the meal-picker keyboard."""
    await on_plan(message, storage, settings)
