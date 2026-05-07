"""Questionnaire FSM handlers.

Flow: sex → age → weight → height → waist (skippable) → activity → goal →
goal_pace → diet_pattern → health_flags (multi-select) → allergies (skippable
free-text) → meals_count → render plan.
"""

from __future__ import annotations

import contextlib
from typing import cast

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from nutrition_bot import keyboards
from nutrition_bot.config import Settings
from nutrition_bot.fsm import Onboarding
from nutrition_bot.handlers.plan import send_plan
from nutrition_bot.nutrition import (
    Activity,
    DietPattern,
    Goal,
    GoalPace,
    HealthFlag,
    Profile,
    Sex,
)
from nutrition_bot.storage import Storage

router = Router(name="onboarding")


def _is_allowed(user_id: int, allowed: list[int]) -> bool:
    return not allowed or user_id in allowed


def _decode_health_set(raw: str) -> frozenset[HealthFlag]:
    if not raw:
        return frozenset()
    out: set[HealthFlag] = set()
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.add(HealthFlag(tok))
        except ValueError:
            continue
    return frozenset(out)


def _encode_health_set(flags: frozenset[HealthFlag]) -> str:
    return ",".join(sorted(f.value for f in flags))


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
            "• /notes — пожелания / ограничения по еде\n"
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
        "⚠️ <i>Важно: я не врач. При заболеваниях согласуй план "
        "с лечащим специалистом.</i>\n\n"
        "Твой биологический пол?",
        reply_markup=keyboards.sex_kb(),
        parse_mode="HTML",
    )


@router.message(Command("reset"))
async def on_reset(
    message: Message, state: FSMContext, storage: Storage, settings: Settings
) -> None:
    if message.from_user is None:
        return
    if not _is_allowed(message.from_user.id, settings.allowed_user_ids):
        await message.answer("Доступ ограничён.")
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
    await state.set_state(Onboarding.waist)
    await message.answer(
        "Окружность талии в см на уровне пупка? (необязательно — нужно для "
        "оценки абдоминального жира). Можешь пропустить.",
        reply_markup=keyboards.skip_kb("skip:waist"),
    )


@router.message(Onboarding.waist)
async def on_waist_text(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        waist = float(message.text.replace(",", ".").strip())
        if not (40 <= waist <= 200):
            raise ValueError
    except ValueError:
        await message.answer(
            "Нужно число от 40 до 200 см или нажми «Пропустить».",
            reply_markup=keyboards.skip_kb("skip:waist"),
        )
        return
    await state.update_data(waist=waist)
    await _ask_activity(message, state)


@router.callback_query(Onboarding.waist, F.data == "skip:waist")
async def on_waist_skip(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None:
        return
    await state.update_data(waist=None)
    await query.answer()
    await _ask_activity(cast(Message, query.message), state)


async def _ask_activity(message: Message, state: FSMContext) -> None:
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
    await cast(Message, query.message).answer(
        "Какая у тебя цель?",
        reply_markup=keyboards.goal_kb(),
    )


@router.callback_query(Onboarding.goal, F.data.startswith("goal:"))
async def on_goal(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None or query.message is None or query.from_user is None:
        return
    goal = Goal(query.data.split(":", 1)[1])
    await state.update_data(goal=goal.value)
    await state.set_state(Onboarding.goal_pace)
    await query.answer()
    await cast(Message, query.message).answer(
        "Как быстро двигаемся к цели?\n\n"
        "<i>Мягкий темп проще удерживать, агрессивный — быстрее результат, но "
        "хуже композиция тела и риск срывов выше.</i>",
        parse_mode="HTML",
        reply_markup=keyboards.goal_pace_kb(),
    )


@router.callback_query(Onboarding.goal_pace, F.data.startswith("pace:"))
async def on_goal_pace(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None or query.message is None:
        return
    pace = GoalPace(query.data.split(":", 1)[1])
    await state.update_data(goal_pace=pace.value)
    await state.set_state(Onboarding.diet_pattern)
    await query.answer()
    await cast(Message, query.message).answer(
        "Выбери стиль питания:\n\n"
        "• <b>Сбалансированный</b> — база, 2 г/кг белка.\n"
        "• <b>Высокобелковый</b> — для тренировочных целей и сохранения мышц.\n"
        "• <b>Низкоуглеводный</b> — углеводы ≤25% ккал.\n"
        "• <b>Средиземноморский</b> — упор на оливковое масло, рыбу, овощи.\n"
        "• <b>Вегетарианский / Веганский</b> — без мяса (и без животных продуктов).",
        parse_mode="HTML",
        reply_markup=keyboards.diet_pattern_kb(),
    )


@router.callback_query(Onboarding.diet_pattern, F.data.startswith("diet:"))
async def on_diet_pattern(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None or query.message is None:
        return
    pattern = DietPattern(query.data.split(":", 1)[1])
    await state.update_data(diet_pattern=pattern.value, health_flags="")
    await state.set_state(Onboarding.health_flags)
    await query.answer()
    await cast(Message, query.message).answer(
        "Есть ли у тебя что-то из списка? Можно отметить несколько пунктов.\n"
        "Это помогает скорректировать план (натрий, насыщенные жиры, углеводы).\n\n"
        "<i>Если ничего нет — нажми «Ничего из перечисленного».</i>",
        parse_mode="HTML",
        reply_markup=keyboards.health_flags_kb(frozenset()),
    )


@router.callback_query(Onboarding.health_flags, F.data.startswith("health:toggle:"))
async def on_health_toggle(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None or query.message is None:
        return
    flag = HealthFlag(query.data.split(":", 2)[2])
    data = await state.get_data()
    current = _decode_health_set(data.get("health_flags", ""))
    new = current.symmetric_difference({flag})
    # Pregnancy trimesters are mutually exclusive — drop the other automatically.
    if flag is HealthFlag.pregnancy_t2 and flag in new:
        new = new - {HealthFlag.pregnancy_t3}
    elif flag is HealthFlag.pregnancy_t3 and flag in new:
        new = new - {HealthFlag.pregnancy_t2}
    await state.update_data(health_flags=_encode_health_set(frozenset(new)))
    await query.answer()
    # Markup edit can race (e.g. user double-clicked); safe to ignore failures.
    with contextlib.suppress(Exception):
        await cast(Message, query.message).edit_reply_markup(
            reply_markup=keyboards.health_flags_kb(frozenset(new))
        )


@router.callback_query(Onboarding.health_flags, F.data == "health:none")
async def on_health_none(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None:
        return
    await state.update_data(health_flags="")
    await query.answer()
    await _ask_allergies(cast(Message, query.message), state)


@router.callback_query(Onboarding.health_flags, F.data == "health:done")
async def on_health_done(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None:
        return
    await query.answer()
    await _ask_allergies(cast(Message, query.message), state)


async def _ask_allergies(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.allergies)
    await message.answer(
        "Аллергии или продукты, которые точно не едим? "
        "(например: «орехи, креветки, лактоза»). "
        "Если ничего — нажми «Пропустить».",
        reply_markup=keyboards.skip_kb("skip:allergies"),
    )


@router.message(Onboarding.allergies)
async def on_allergies_text(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    text = message.text.strip()
    if text == "-":
        text = ""
    await state.update_data(allergies=text)
    await _ask_meals_count(message, state)


@router.callback_query(Onboarding.allergies, F.data == "skip:allergies")
async def on_allergies_skip(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None:
        return
    await state.update_data(allergies="")
    await query.answer()
    await _ask_meals_count(cast(Message, query.message), state)


async def _ask_meals_count(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.meals_count)
    await message.answer(
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
    waist_raw = data.get("waist")
    waist_cm = float(waist_raw) if isinstance(waist_raw, (int, float)) else None
    health_flags = _decode_health_set(data.get("health_flags", ""))
    try:
        profile = Profile(
            sex=Sex(data["sex"]),
            age=int(data["age"]),
            weight_kg=float(data["weight"]),
            height_cm=float(data["height"]),
            activity=Activity(data["activity"]),
            goal=Goal(data["goal"]),
            waist_cm=waist_cm,
            diet_pattern=DietPattern(data.get("diet_pattern", "balanced")),
            goal_pace=GoalPace(data.get("goal_pace", "standard")),
            health_flags=health_flags,
            allergies=data.get("allergies", "") or "",
        )
    except ValueError as exc:
        # E.g. pregnancy + sex=male — restart the questionnaire.
        await query.answer(f"Несовместимые ответы: {exc}", show_alert=True)
        await state.clear()
        await state.set_state(Onboarding.sex)
        await cast(Message, query.message).answer(
            "Несовместимый набор ответов. Заполняем заново.\n\nТвой биологический пол?",
            reply_markup=keyboards.sex_kb(),
        )
        return
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
