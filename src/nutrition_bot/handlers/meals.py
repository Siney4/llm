"""Meal generation handlers: turns kcal targets into concrete dish ideas via the LLM."""

from __future__ import annotations

import contextlib
import html
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from nutrition_bot import keyboards
from nutrition_bot.config import Settings
from nutrition_bot.fsm import DietNotesEdit
from nutrition_bot.llm import MealGenerator, MealRequest
from nutrition_bot.nutrition import MEAL_LABELS_RU, Macros, build_plan
from nutrition_bot.storage import Storage

router = Router(name="meals")
log = logging.getLogger(__name__)


def _meal_macro_share(
    meal_key: str, daily: Macros, meal_kcal: int, daily_kcal: int
) -> tuple[int, int, int]:
    """Pro-rate daily macros to a single meal by its kcal share."""
    if daily_kcal <= 0:
        return 0, 0, 0
    share = meal_kcal / daily_kcal
    return (
        int(round(daily.protein_g * share)),
        int(round(daily.fat_g * share)),
        int(round(daily.carbs_g * share)),
    )


@router.message(Command("meal"))
async def on_meal_command(message: Message, storage: Storage, settings: Settings) -> None:
    if message.from_user is None:
        return
    saved = await storage.load_profile(message.from_user.id)
    if saved is None:
        await message.answer("Сначала заполни анкету: /start")
        return
    profile, meals_count, _ = saved
    plan = build_plan(
        profile, meals_count=meals_count or 4, buffer_fraction=settings.buffer_fraction
    )
    meal_keys = tuple(m.key for m in plan.meals)
    await message.answer(
        "Какой приём пищи сгенерировать?",
        reply_markup=keyboards.meal_pick_kb(meal_keys, plan.buffer_kcal),
    )


@router.message(Command("notes"))
async def on_notes_command(message: Message, state: FSMContext) -> None:
    await state.set_state(DietNotesEdit.awaiting)
    await message.answer(
        "Пришли свободным текстом ограничения / пожелания по еде "
        "(например: «без свинины», «вегетарианец», «не ем рыбу»).\n"
        "Чтобы очистить — отправь «-»."
    )


@router.message(DietNotesEdit.awaiting)
async def on_notes_set(message: Message, state: FSMContext, storage: Storage) -> None:
    if message.from_user is None or message.text is None:
        return
    notes = message.text.strip()
    if notes == "-":
        notes = ""
    await storage.update_diet_notes(message.from_user.id, notes)
    await state.clear()
    await message.answer("Ограничения сохранены ✅" if notes else "Ограничения очищены.")


@router.callback_query(F.data.startswith("gen:"))
async def on_generate(
    query: CallbackQuery,
    storage: Storage,
    settings: Settings,
    llm: MealGenerator,
) -> None:
    if query.data is None or query.message is None or query.from_user is None:
        return
    meal_key = query.data.split(":", 1)[1]
    saved = await storage.load_profile(query.from_user.id)
    if saved is None:
        await query.answer("Профиль не найден, заполни /start", show_alert=True)
        return
    profile, meals_count, diet_notes = saved
    plan = build_plan(
        profile, meals_count=meals_count or 4, buffer_fraction=settings.buffer_fraction
    )

    if meal_key == "buffer":
        target_kcal = plan.buffer_kcal
        meal_label = "Вкусняшка из буфера (правило 80/20)"
        macro_share: tuple[int, int, int] | None = None
    else:
        meal = next((m for m in plan.meals if m.key == meal_key), None)
        if meal is None:
            await query.answer("Неизвестный приём пищи", show_alert=True)
            return
        target_kcal = meal.kcal
        meal_label = MEAL_LABELS_RU.get(meal_key, meal.label)
        macro_share = _meal_macro_share(meal_key, plan.macros, meal.kcal, plan.target_kcal)

    await query.answer("Генерирую…")
    placeholder = await _safe_send(
        query, f"⏳ Подбираю вариант для «{meal_label}» на ~{target_kcal} ккал…"
    )

    req = MealRequest(
        meal_label=meal_label,
        target_kcal=target_kcal,
        target_protein_g=macro_share[0] if macro_share else None,
        target_fat_g=macro_share[1] if macro_share else None,
        target_carbs_g=macro_share[2] if macro_share else None,
        diet_notes=diet_notes or None,
    )
    try:
        text = await llm.generate(profile, plan.macros, req)
    except Exception as exc:  # noqa: BLE001 — surface LLM errors to the user
        log.exception("LLM generation failed")
        await _safe_edit(
            placeholder,
            (
                f"❌ Не удалось получить ответ от LLM: {html.escape(str(exc))}\n"
                f"Проверь, что Qwen2.5-14B-Instruct запущен и доступен по "
                f"{html.escape(settings.openai_base_url)}."
            ),
        )
        return

    # LLM output is plain user text — escape so any '<', '>', '&' in cooking notes
    # don't break HTML parse mode (Telegram would otherwise reject the message).
    final = f"🍽 <b>{html.escape(meal_label)}</b> · цель ~{target_kcal} ккал\n\n{html.escape(text)}"
    await _safe_edit(placeholder, final, reply_markup=keyboards.post_meal_kb(meal_key))


async def _safe_send(query: CallbackQuery, text: str) -> Message:
    msg: Message | None = None
    with contextlib.suppress(TelegramBadRequest):
        msg = await query.message.answer(text)  # type: ignore[union-attr]
    if msg is None:
        msg = await query.bot.send_message(query.from_user.id, text)  # type: ignore[union-attr]
    return msg


async def _safe_edit(message: Message, text: str, reply_markup: object | None = None) -> None:
    """Edit-or-resend, with a final plain-text fallback so messages always land."""
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)  # type: ignore[arg-type]
        return
    except TelegramBadRequest:
        pass
    try:
        await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)  # type: ignore[arg-type]
        return
    except TelegramBadRequest:
        log.warning("HTML send failed; retrying as plain text")
    # Last resort: drop parse_mode so even malformed HTML still reaches the user.
    await message.answer(text, reply_markup=reply_markup)  # type: ignore[arg-type]
