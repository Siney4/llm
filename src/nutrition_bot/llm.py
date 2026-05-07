"""LLM client and prompt builders for meal generation.

Uses the OpenAI Python SDK against an OpenAI-compatible endpoint so the same
code works with llama.cpp's ``llama-server``, Ollama, vLLM, LM Studio, etc.
The default target is **Qwen2.5-14B-Instruct Q4_K_M** running locally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from nutrition_bot.nutrition import (
    DIET_PATTERN_LABELS_RU,
    HEALTH_FLAG_LABELS_RU,
    DietPattern,
    HealthFlag,
    Macros,
    Plan,
    Profile,
)

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты — диетолог-нутрициолог. Тебе дают данные пользователя и целевой калораж "
    "приёма пищи. Твоя задача — предложить ОДИН конкретный вариант блюда (или "
    "набор блюд для одного приёма пищи) на русском языке.\n\n"
    "Жёсткие правила:\n"
    "1. Калораж блюда должен попадать в коридор ±10% от целевого.\n"
    "2. Указывай вес каждого ингредиента в граммах (или мл).\n"
    "3. Указывай итоговое КБЖУ (ккал, белки, жиры, углеводы) и КБЖУ на 100 г, "
    "если это уместно.\n"
    "4. Никаких подзаголовков «Введение», «Заключение». Сразу к делу.\n"
    "5. Никакого markdown с #/##; используй обычный текст и эмодзи в меру.\n"
    "6. Считай как калькулятор, а не художник: значения округляй разумно.\n"
    "7. Никогда не выдумывай ингредиенты, которых не существует.\n"
    "8. ОБЯЗАТЕЛЬНО уважай аллергии и медицинские ограничения — если "
    "пользователь не ест продукт, он не должен оказаться в блюде.\n"
    "9. Это не медицинский совет; при наличии заболеваний пользователь "
    "консультируется с врачом."
)


# Pattern-specific guidance injected into the system message at request time.
_PATTERN_HINTS: dict[DietPattern, str] = {
    DietPattern.balanced: "",
    DietPattern.high_protein: (
        "Стиль высокобелковый: приоритет — постное мясо, рыба, яйца, "
        "творог; на каждый приём пищи белок ≥ 30 г, если позволяет калораж."
    ),
    DietPattern.low_carb: (
        "Стиль низкоуглеводный: углеводов ≤ 30 г на приём, основа — "
        "белок и жиры (рыба, яйца, авокадо, оливковое масло, овощи)."
    ),
    DietPattern.mediterranean: (
        "Стиль средиземноморский: оливковое масло, рыба, бобовые, "
        "цельные злаки, овощи, орехи; красное мясо — редко."
    ),
    DietPattern.vegetarian: (
        "Вегетарианский стиль: НЕ используй мясо и рыбу. "
        "Молочка и яйца допустимы. Делай упор на бобовые, тофу, темпе."
    ),
    DietPattern.vegan: (
        "Веганский стиль: НИКАКИХ продуктов животного происхождения "
        "(мясо, рыба, яйца, молочка, мёд). Источники белка — бобовые, "
        "тофу, темпе, сейтан, протеиновые порошки на растительной основе."
    ),
}


_FLAG_HINTS: dict[HealthFlag, str] = {
    HealthFlag.hypertension: (
        "Гипертония: натрий ≤ 1500 мг/сутки. Не используй "
        "колбасы / соусы / промышленные соусы / соевый соус."
    ),
    HealthFlag.pre_diabetes: (
        "Пред-диабет: углеводы преимущественно цельнозерновые / бобовые, "
        "избегай сахара и быстрых углеводов; на тарелке всегда клетчатка."
    ),
    HealthFlag.diabetes_t2: (
        "Сахарный диабет 2: низкий гликемический индекс, углеводы ≤ 30% ккал, "
        "никаких сахаросодержащих напитков и сладостей."
    ),
    HealthFlag.high_cholesterol: (
        "Высокий холестерин: насыщенные жиры ≤ 7% ккал, замени их на "
        "моно/полиненасыщенные (рыба, оливковое, орехи)."
    ),
    HealthFlag.kidney_concerns: (
        "Проблемы с почками: белок ≤ 1.0 г/кг/сутки. Минимизируй продукты "
        "с высоким содержанием фосфора (плавленые сыры, кола, переработанное мясо). "
        "Пользователь должен согласовать рацион с нефрологом."
    ),
    HealthFlag.pregnancy_t2: (
        "Беременность 2 триместр: +340 ккал и +25 г белка к норме. "
        "Запрещены: сырая рыба/мясо, мягкие сыры из непастеризованного молока, "
        "большие хищные рыбы (тунец, меч-рыба), алкоголь."
    ),
    HealthFlag.pregnancy_t3: (
        "Беременность 3 триместр: +450 ккал и +25 г белка. "
        "Запрещены: сырая рыба/мясо, мягкие сыры из непастеризованного молока, "
        "большие хищные рыбы, алкоголь, печень (избыток витамина А)."
    ),
    HealthFlag.breastfeeding: (
        "Грудное вскармливание: +500 ккал и +20 г белка. Достаточно жидкости. "
        "Алкоголь и большие хищные рыбы — исключить."
    ),
}


@dataclass(frozen=True, slots=True)
class MealRequest:
    """Inputs for a single meal generation."""

    meal_label: str
    target_kcal: int
    target_protein_g: int | None = None
    target_fat_g: int | None = None
    target_carbs_g: int | None = None
    diet_notes: str | None = None  # legacy free-form notes from /notes
    sodium_cap_mg: int | None = None
    saturated_fat_cap_g: int | None = None
    fiber_target_g: int | None = None


def _system_prompt(profile: Profile) -> str:
    """System prompt + pattern/health hints baked in."""
    extra: list[str] = []
    pattern_hint = _PATTERN_HINTS.get(profile.diet_pattern, "")
    if pattern_hint:
        extra.append(pattern_hint)
    for flag in sorted(profile.health_flags, key=lambda f: f.value):
        extra.append(_FLAG_HINTS[flag])
    if not extra:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + "\n\nКонтекст пользователя:\n- " + "\n- ".join(extra)


def build_user_prompt(profile: Profile, daily_macros: Macros, req: MealRequest) -> str:
    """Build a deterministic user prompt for the LLM."""
    sex_ru = "мужчина" if profile.sex.value == "male" else "женщина"
    lines = [
        f"Пользователь: {sex_ru}, {profile.age} лет, {profile.weight_kg:.0f} кг, "
        f"{profile.height_cm:.0f} см.",
        f"Целевой КБЖУ на день: {daily_macros.kcal} ккал · "
        f"Б {daily_macros.protein_g} г / Ж {daily_macros.fat_g} г / "
        f"У {daily_macros.carbs_g} г.",
        f"Стиль питания: {DIET_PATTERN_LABELS_RU[profile.diet_pattern]}.",
    ]
    if profile.health_flags:
        labels = ", ".join(
            HEALTH_FLAG_LABELS_RU[f] for f in sorted(profile.health_flags, key=lambda x: x.value)
        )
        lines.append(f"Состояния здоровья: {labels}.")
    if profile.allergies:
        lines.append(f"АЛЛЕРГИИ / ИСКЛЮЧИТЬ ПОЛНОСТЬЮ: {profile.allergies}.")

    lines.extend(
        [
            "",
            f"Сейчас нужен ОДИН приём пищи: {req.meal_label}.",
            f"Целевая калорийность приёма: {req.target_kcal} ккал (±10%).",
        ]
    )

    macro_targets: list[str] = []
    if req.target_protein_g is not None:
        macro_targets.append(f"Б ~{req.target_protein_g} г")
    if req.target_fat_g is not None:
        macro_targets.append(f"Ж ~{req.target_fat_g} г")
    if req.target_carbs_g is not None:
        macro_targets.append(f"У ~{req.target_carbs_g} г")
    if macro_targets:
        lines.append("Желательное распределение макросов: " + " · ".join(macro_targets) + ".")

    daily_caps: list[str] = []
    if req.sodium_cap_mg is not None:
        daily_caps.append(f"натрий ≤ {req.sodium_cap_mg} мг/сутки")
    if req.saturated_fat_cap_g is not None:
        daily_caps.append(f"насыщ. жиры ≤ {req.saturated_fat_cap_g} г/сутки")
    if req.fiber_target_g is not None:
        daily_caps.append(f"клетчатка ≥ {req.fiber_target_g} г/сутки")
    if daily_caps:
        lines.append("Дневные ориентиры: " + " · ".join(daily_caps) + ".")

    if req.diet_notes:
        lines.append(f"Дополнительно (свободный текст): {req.diet_notes}")

    lines.extend(
        [
            "",
            "Ответ оформи строго так:",
            "🍽 <название блюда>",
            "Ингредиенты:",
            "• <ингредиент> — <вес> г",
            "...",
            "Приготовление: 2–4 коротких шага.",
            "Итог: ~<ккал> ккал · Б <г> / Ж <г> / У <г>.",
        ]
    )
    return "\n".join(lines)


def request_from_plan(
    plan: Plan,
    *,
    meal_label: str,
    target_kcal: int,
    macro_share: tuple[int, int, int] | None,
    diet_notes: str | None,
) -> MealRequest:
    """Build a MealRequest from an active Plan, threading daily caps through."""
    return MealRequest(
        meal_label=meal_label,
        target_kcal=target_kcal,
        target_protein_g=macro_share[0] if macro_share else None,
        target_fat_g=macro_share[1] if macro_share else None,
        target_carbs_g=macro_share[2] if macro_share else None,
        diet_notes=diet_notes,
        sodium_cap_mg=plan.sodium_cap_mg,
        saturated_fat_cap_g=plan.saturated_fat_cap_g,
        fiber_target_g=plan.fiber_g,
    )


class MealGenerator:
    """Thin async wrapper around the OpenAI-compatible chat-completions API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 900,
        timeout_s: float = 120.0,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "sk-no-key-required",
            timeout=timeout_s,
        )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def close(self) -> None:
        await self._client.close()

    async def generate(self, profile: Profile, daily_macros: Macros, req: MealRequest) -> str:
        user_prompt = build_user_prompt(profile, daily_macros, req)
        system_prompt = _system_prompt(profile)
        log.debug("LLM call (model=%s, target_kcal=%d)", self._model, req.target_kcal)
        resp = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if not resp.choices:
            raise RuntimeError("LLM returned no choices")
        content = resp.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content.strip()
