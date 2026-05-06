"""Questionnaire FSM handlers: sex → age → weight → height → activity → goal."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from nutrition_bot import keyboards
from nutrition_bot.config import Settings
from nutrition_bot.fsm import Onboarding
from nutrition_bot.handlers.plan import send_plan
from nutrition_bot.nutrition import Activity, Goal, Profile, Sex
from nutrition_bot.storage import Storage

router = Router(name="onboarding")


def _is_allowed(user_id: int, allowed: list[int]) -> bool:
    return not allowed or user_id in allowed


@router.message(CommandStart())
async def on_start(
    message: Message, state: FSMContext, storage: Storage, settings: Settings
) -> None:
    if message.from_user is None:
        return
    if not _is_allowed(message.from_user.id, settings.allowed_user_ids):
        await message.answer("Доступ ограничён.")
        return

    saved = await storage.load_profile(message.from_user.id)
    if saved is not None and saved[1] is not None:
        profile, meals_count, _ = saved
        await message.answer(
            "Привет! У меня уже сохранён твой профиль. Показываю план.\n\n"
            "Команды:\n"
            "• /plan — текущий план питания\n"
            "• /meal — сгенерировать блюдо\n"
            "• /reset — заполнить анкету заново"
        )
        await send_plan(
            chat_id=message.chat.id,
            bot=message.bot,  # type: ignore[arg-type]
            profile=profile,
            meals_count=meals_count or 4,
            buffer_fraction=settings.buffer_fraction,
        )
        return

    await state.clear()
    await state.set_state(Onboarding.sex)
    await message.answer(
        "Привет! Я помогу составить персональный план питания.\n"
        "Сначала пара вопросов — займёт минуту.\n\n"
        "Твой биологический пол?",
        reply_markup=keyboards.sex_kb(),
    )


@router.message(Command("reset"))
async def on_reset(message: Message, state: FSMContext, storage: Storage) -> None:
    if message.from_user is None:
        return
    await storage.delete_profile(message.from_user.id)
    await state.clear()
    await state.set_state(Onboarding.sex)
    await message.answer(
        "Профиль очищен. Заполним заново.\n\nТвой биологический пол?",
        reply_markup=keyboards.sex_kb(),
    )


@router.callback_query(Onboarding.sex, F.data.startswith("sex:"))
async def on_sex(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None or query.message is None:
        return
    sex = Sex(query.data.split(":", 1)[1])
    await state.update_data(sex=sex.value)
    await state.set_state(Onboarding.age)
    await query.answer()
    await query.message.answer("Сколько тебе лет? (число от 10 до 100)")


@router.message(Onboarding.age)
async def on_age(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        age = int(message.text.strip())
        if not (10 <= age <= 100):
            raise ValueError
    except ValueError:
        await message.answer("Нужно целое число от 10 до 100. Попробуй ещё раз.")
        return
    await state.update_data(age=age)
    await state.set_state(Onboarding.weight)
    await message.answer("Твой вес в кг? (например 72.5)")


@router.message(Onboarding.weight)
async def on_weight(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        weight = float(message.text.replace(",", ".").strip())
        if not (30 <= weight <= 300):
            raise ValueError
    except ValueError:
        await message.answer("Нужно число от 30 до 300 кг. Попробуй ещё раз.")
        return
    await state.update_data(weight=weight)
    await state.set_state(Onboarding.height)
    await message.answer("Твой рост в см? (например 178)")


@router.message(Onboarding.height)
async def on_height(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        height = float(message.text.replace(",", ".").strip())
        if not (120 <= height <= 230):
            raise ValueError
    except ValueError:
        await message.answer("Нужно число от 120 до 230 см. Попробуй ещё раз.")
        return
    await state.update_data(height=height)
    await state.set_state(Onboarding.activity)
    await message.answer(
        "Уровень повседневной активности:",
        reply_markup=keyboards.activity_kb(),
    )


@router.callback_query(Onboarding.activity, F.data.startswith("activity:"))
async def on_activity(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None or query.message is None:
        return
    activity = Activity(query.data.split(":", 1)[1])
    await state.update_data(activity=activity.value)
    await state.set_state(Onboarding.goal)
    await query.answer()
    await query.message.answer(
        "Какая у тебя цель?",
        reply_markup=keyboards.goal_kb(),
    )


@router.callback_query(Onboarding.goal, F.data.startswith("goal:"))
async def on_goal(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None or query.message is None or query.from_user is None:
        return
    goal = Goal(query.data.split(":", 1)[1])
    await state.update_data(goal=goal.value)
    await state.set_state(Onboarding.meals_count)
    await query.answer()
    await query.message.answer(
        "Сколько приёмов пищи в день тебе удобно?",
        reply_markup=keyboards.meals_count_kb(),
    )


@router.callback_query(Onboarding.meals_count, F.data.startswith("meals:"))
async def on_meals_count(
    query: CallbackQuery,
    state: FSMContext,
    storage: Storage,
    settings: Settings,
) -> None:
    if query.data is None or query.message is None or query.from_user is None:
        return
    meals_count = int(query.data.split(":", 1)[1])
    if meals_count not in (3, 4, 5):
        await query.answer("Допустимо 3, 4 или 5", show_alert=True)
        return

    data = await state.get_data()
    profile = Profile(
        sex=Sex(data["sex"]),
        age=int(data["age"]),
        weight_kg=float(data["weight"]),
        height_cm=float(data["height"]),
        activity=Activity(data["activity"]),
        goal=Goal(data["goal"]),
    )
    await storage.save_profile(query.from_user.id, profile, meals_count=meals_count)
    await state.clear()
    await query.answer()
    await send_plan(
        chat_id=query.message.chat.id,
        bot=query.bot,  # type: ignore[arg-type]
        profile=profile,
        meals_count=meals_count,
        buffer_fraction=settings.buffer_fraction,
    )
