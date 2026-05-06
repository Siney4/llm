"""Inline keyboards used by the bot (questionnaire + meal selection)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from nutrition_bot.nutrition import (
    ACTIVITY_LABELS_RU,
    GOAL_LABELS_RU,
    Activity,
    Goal,
)


def sex_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Мужчина", callback_data="sex:male"),
                InlineKeyboardButton(text="👩 Женщина", callback_data="sex:female"),
            ]
        ]
    )


def activity_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=ACTIVITY_LABELS_RU[a], callback_data=f"activity:{a.value}")]
        for a in Activity
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def goal_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=GOAL_LABELS_RU[g], callback_data=f"goal:{g.value}")]
        for g in Goal
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def meals_count_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="3", callback_data="meals:3"),
                InlineKeyboardButton(text="4", callback_data="meals:4"),
                InlineKeyboardButton(text="5", callback_data="meals:5"),
            ]
        ]
    )


def meal_pick_kb(meal_keys: tuple[str, ...], buffer_kcal: int) -> InlineKeyboardMarkup:
    """Keyboard listing every meal slot of the active plan + the buffer."""
    from nutrition_bot.nutrition import MEAL_LABELS_RU

    rows: list[list[InlineKeyboardButton]] = []
    for k in meal_keys:
        rows.append([InlineKeyboardButton(text=MEAL_LABELS_RU[k], callback_data=f"gen:{k}")])
    if buffer_kcal > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🍩 Вкусняшка из буфера ({buffer_kcal} ккал)",
                    callback_data="gen:buffer",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_meal_kb(meal_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Другой вариант", callback_data=f"gen:{meal_key}"),
                InlineKeyboardButton(text="📋 К плану", callback_data="back:plan"),
            ]
        ]
    )
