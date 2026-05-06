"""LLM client and prompt builders for meal generation.

Uses the OpenAI Python SDK against an OpenAI-compatible endpoint so the same
code works with llama.cpp's ``llama-server``, Ollama, vLLM, LM Studio, etc.
The default target is **Qwen2.5-14B-Instruct Q4_K_M** running locally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from nutrition_bot.nutrition import Macros, Profile

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
    "7. Никогда не выдумывай ингредиенты, которых не существует."
)


@dataclass(frozen=True, slots=True)
class MealRequest:
    """Inputs for a single meal generation."""

    meal_label: str
    target_kcal: int
    target_protein_g: int | None = None
    target_fat_g: int | None = None
    target_carbs_g: int | None = None
    diet_notes: str | None = None  # free-form: e.g. "без свинины", "вегетарианец"


def build_user_prompt(profile: Profile, daily_macros: Macros, req: MealRequest) -> str:
    """Build a deterministic user prompt for the LLM."""
    sex_ru = "мужчина" if profile.sex.value == "male" else "женщина"
    lines = [
        f"Пользователь: {sex_ru}, {profile.age} лет, {profile.weight_kg:.0f} кг, "
        f"{profile.height_cm:.0f} см.",
        f"Целевой КБЖУ на день: {daily_macros.kcal} ккал · "
        f"Б {daily_macros.protein_g} г / Ж {daily_macros.fat_g} г / "
        f"У {daily_macros.carbs_g} г.",
        "",
        f"Сейчас нужен ОДИН приём пищи: {req.meal_label}.",
        f"Целевая калорийность приёма: {req.target_kcal} ккал (±10%).",
    ]
    macro_targets: list[str] = []
    if req.target_protein_g is not None:
        macro_targets.append(f"Б ~{req.target_protein_g} г")
    if req.target_fat_g is not None:
        macro_targets.append(f"Ж ~{req.target_fat_g} г")
    if req.target_carbs_g is not None:
        macro_targets.append(f"У ~{req.target_carbs_g} г")
    if macro_targets:
        lines.append("Желательное распределение макросов: " + " · ".join(macro_targets) + ".")
    if req.diet_notes:
        lines.append(f"Ограничения / пожелания: {req.diet_notes}")

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
        log.debug("LLM call (model=%s, target_kcal=%d)", self._model, req.target_kcal)
        resp = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        if not resp.choices:
            raise RuntimeError("LLM returned no choices")
        content = resp.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content.strip()
