"""Plain-text formatters for plan / meal display in Telegram messages.

Output of these helpers is sent with ``parse_mode="HTML"``, so any user-facing
label that may contain ``<``, ``>`` or ``&`` (e.g. the sedentary activity
label "< 5 000 шагов") is HTML-escaped before interpolation.
"""

from __future__ import annotations

from html import escape

from nutrition_bot.nutrition import (
    ACTIVITY_LABELS_RU,
    GOAL_LABELS_RU,
    PAL,
    Plan,
    Profile,
)


def format_profile(profile: Profile) -> str:
    sex_ru = "Мужчина" if profile.sex.value == "male" else "Женщина"
    return (
        f"👤 {sex_ru}, {profile.age} лет\n"
        f"⚖️ {profile.weight_kg:.0f} кг · 📏 {profile.height_cm:.0f} см\n"
        f"🏃 Активность: {escape(ACTIVITY_LABELS_RU[profile.activity])} "
        f"(×{PAL[profile.activity]})\n"
        f"🎯 Цель: {escape(GOAL_LABELS_RU[profile.goal])}"
    )


def format_plan(profile: Profile, plan: Plan) -> str:
    lines = [
        format_profile(profile),
        "",
        f"🔥 BMR (базовый обмен): <b>{plan.bmr}</b> ккал",
        f"⚡ TDEE (общий расход): <b>{plan.tdee}</b> ккал",
        f"🎯 Целевой калораж: <b>{plan.target_kcal}</b> ккал/сутки",
        "",
        "🍎 КБЖУ на день:",
        f"• Белки: <b>{plan.macros.protein_g} г</b> (~{plan.macros.protein_g * 4} ккал)",
        f"• Жиры:  <b>{plan.macros.fat_g} г</b> (~{plan.macros.fat_g * 9} ккал)",
        f"• Углеводы: <b>{plan.macros.carbs_g} г</b> (~{plan.macros.carbs_g * 4} ккал)",
        "",
        f"🍽 Раскладка на {len(plan.meals)} приёма(ов):",
    ]
    for meal in plan.meals:
        lines.append(f"• {meal.label}: <b>{meal.kcal}</b> ккал")
    if plan.buffer_kcal > 0:
        lines.append(f"• 🍩 Буфер на вкусняшки: <b>{plan.buffer_kcal}</b> ккал (правило 80/20)")
    lines.extend(
        [
            "",
            "Жми /meal — сгенерирую конкретный вариант блюда под нужный приём.",
        ]
    )
    return "\n".join(lines)
