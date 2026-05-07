"""Plain-text formatters for plan / meal display in Telegram messages.

Output of these helpers is sent with ``parse_mode="HTML"``, so any user-facing
label that may contain ``<``, ``>`` or ``&`` (e.g. the sedentary activity
label "< 5 000 шагов") is HTML-escaped before interpolation. User-supplied
free-form fields (allergies, diet notes) are also escaped.
"""

from __future__ import annotations

from html import escape

from nutrition_bot.nutrition import (
    ACTIVITY_LABELS_RU,
    BMI_CATEGORY_LABELS_RU,
    DIET_PATTERN_LABELS_RU,
    GOAL_LABELS_RU,
    GOAL_PACE_LABELS_RU,
    HEALTH_FLAG_LABELS_RU,
    PAL,
    WAIST_RISK_LABELS_RU,
    DietPattern,
    GoalPace,
    Plan,
    Profile,
)


def _profile_extras(profile: Profile) -> list[str]:
    out: list[str] = []
    if profile.diet_pattern is not DietPattern.balanced:
        out.append(f"🥗 Стиль: {escape(DIET_PATTERN_LABELS_RU[profile.diet_pattern])}")
    if profile.goal_pace is not GoalPace.standard:
        out.append(f"⏱ Темп: {escape(GOAL_PACE_LABELS_RU[profile.goal_pace])}")
    if profile.waist_cm is not None:
        out.append(f"📐 Талия: {profile.waist_cm:.0f} см")
    if profile.health_flags:
        labels = ", ".join(
            HEALTH_FLAG_LABELS_RU[f] for f in sorted(profile.health_flags, key=lambda x: x.value)
        )
        out.append(f"🩺 Здоровье: {escape(labels)}")
    if profile.allergies:
        out.append(f"⚠️ Аллергии: {escape(profile.allergies)}")
    return out


def format_profile(profile: Profile) -> str:
    sex_ru = "Мужчина" if profile.sex.value == "male" else "Женщина"
    base = [
        f"👤 {sex_ru}, {profile.age} лет",
        f"⚖️ {profile.weight_kg:.0f} кг · 📏 {profile.height_cm:.0f} см",
        f"🏃 Активность: {escape(ACTIVITY_LABELS_RU[profile.activity])} (×{PAL[profile.activity]})",
        f"🎯 Цель: {escape(GOAL_LABELS_RU[profile.goal])}",
    ]
    base.extend(_profile_extras(profile))
    return "\n".join(base)


def format_plan(profile: Profile, plan: Plan) -> str:
    lines = [
        format_profile(profile),
        "",
        f"🔥 BMR (базовый обмен): <b>{plan.bmr}</b> ккал",
        f"⚡ TDEE (общий расход): <b>{plan.tdee}</b> ккал",
        f"🎯 Целевой калораж: <b>{plan.target_kcal}</b> ккал/сутки",
        "",
        f"📊 ИМТ: <b>{plan.bmi:.1f}</b> ({escape(BMI_CATEGORY_LABELS_RU[plan.bmi_category])})",
    ]
    if plan.waist_to_height is not None and plan.waist_risk is not None:
        lines.append(
            f"📐 Талия / рост: <b>{plan.waist_to_height:.2f}</b> "
            f"({escape(WAIST_RISK_LABELS_RU[plan.waist_risk])})"
        )

    lines.extend(
        [
            "",
            "🍎 КБЖУ на день:",
            f"• Белки: <b>{plan.macros.protein_g} г</b> (~{plan.macros.protein_g * 4} ккал)",
            f"• Жиры:  <b>{plan.macros.fat_g} г</b> (~{plan.macros.fat_g * 9} ккал)",
            f"• Углеводы: <b>{plan.macros.carbs_g} г</b> (~{plan.macros.carbs_g * 4} ккал)",
            "",
            "📋 Здоровые ориентиры на день:",
            f"• 💧 Вода: <b>~{plan.hydration_l} л</b>",
            f"• 🌾 Клетчатка: <b>≥{plan.fiber_g} г</b>",
            f"• 🧂 Натрий: <b>≤{plan.sodium_cap_mg} мг</b>",
            f"• 🥓 Насыщенные жиры: <b>≤{plan.saturated_fat_cap_g} г</b>",
            "",
            f"🍽 Раскладка на {len(plan.meals)} приёма(ов):",
        ]
    )
    for meal in plan.meals:
        lines.append(f"• {meal.label}: <b>{meal.kcal}</b> ккал")
    if plan.buffer_kcal > 0:
        lines.append(f"• 🍩 Буфер на вкусняшки: <b>{plan.buffer_kcal}</b> ккал (правило 80/20)")

    if plan.warnings:
        lines.extend(["", "⚠️ <b>Важно:</b>"])
        for w in plan.warnings:
            lines.append(f"• {escape(w)}")

    lines.extend(
        [
            "",
            "<i>Это не медицинский совет. План — стартовая точка; "
            "при заболеваниях согласуй с врачом.</i>",
            "",
            "Жми /meal — сгенерирую конкретный вариант блюда под нужный приём.",
        ]
    )
    return "\n".join(lines)
