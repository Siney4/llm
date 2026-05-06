"""Unit tests for the LLM prompt builder (no network)."""

from __future__ import annotations

from nutrition_bot.llm import MealRequest, build_user_prompt
from nutrition_bot.nutrition import Activity, Goal, Macros, Profile, Sex


def test_prompt_includes_anthropometrics_and_target() -> None:
    profile = Profile(
        sex=Sex.male,
        age=30,
        weight_kg=80,
        height_cm=180,
        activity=Activity.moderate,
        goal=Goal.maintain,
    )
    daily = Macros(protein_g=160, fat_g=80, carbs_g=260)
    req = MealRequest(
        meal_label="Завтрак",
        target_kcal=600,
        target_protein_g=40,
        target_fat_g=20,
        target_carbs_g=60,
    )

    prompt = build_user_prompt(profile, daily, req)
    assert "мужчина" in prompt
    assert "30 лет" in prompt
    assert "80 кг" in prompt
    assert "180 см" in prompt
    assert "Завтрак" in prompt
    assert "600 ккал" in prompt
    assert "40" in prompt and "20" in prompt and "60" in prompt
    # Daily KБЖУ is rendered.
    assert "160 г" in prompt
    assert "260 г" in prompt


def test_prompt_includes_diet_notes() -> None:
    profile = Profile(
        sex=Sex.female,
        age=28,
        weight_kg=60,
        height_cm=165,
        activity=Activity.light,
        goal=Goal.cut,
    )
    daily = Macros(protein_g=120, fat_g=60, carbs_g=180)
    req = MealRequest(
        meal_label="Обед",
        target_kcal=550,
        diet_notes="без свинины, не ем грибы",
    )
    prompt = build_user_prompt(profile, daily, req)
    assert "без свинины" in prompt
    assert "грибы" in prompt
    assert "женщина" in prompt


def test_prompt_no_macros_when_unspecified() -> None:
    profile = Profile(
        sex=Sex.male,
        age=30,
        weight_kg=80,
        height_cm=180,
        activity=Activity.moderate,
        goal=Goal.maintain,
    )
    daily = Macros(protein_g=160, fat_g=80, carbs_g=260)
    req = MealRequest(meal_label="Буфер", target_kcal=350)
    prompt = build_user_prompt(profile, daily, req)
    assert "Желательное распределение макросов" not in prompt
