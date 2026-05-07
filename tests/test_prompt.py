"""Unit tests for the LLM prompt builder (no network)."""

from __future__ import annotations

from nutrition_bot.llm import (
    MealRequest,
    _system_prompt,
    build_user_prompt,
    request_from_plan,
)
from nutrition_bot.nutrition import (
    Activity,
    DietPattern,
    Goal,
    HealthFlag,
    Macros,
    Profile,
    Sex,
    build_plan,
)


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
    assert "160 г" in prompt
    assert "260 г" in prompt
    assert "Сбалансированный" in prompt


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


def test_prompt_includes_health_flags_and_allergies() -> None:
    profile = Profile(
        sex=Sex.male,
        age=55,
        weight_kg=92,
        height_cm=178,
        activity=Activity.light,
        goal=Goal.cut,
        diet_pattern=DietPattern.mediterranean,
        health_flags=frozenset({HealthFlag.hypertension, HealthFlag.high_cholesterol}),
        allergies="орехи, креветки",
    )
    plan = build_plan(profile, meals_count=4)
    daily = plan.macros
    req = request_from_plan(
        plan,
        meal_label="Обед",
        target_kcal=plan.meals[1].kcal,
        macro_share=(40, 20, 60),
        diet_notes=None,
    )
    user_prompt = build_user_prompt(profile, daily, req)
    sys_prompt = _system_prompt(profile)
    assert "Гипертония" in user_prompt
    assert "Высокий холестерин" in user_prompt
    assert "АЛЛЕРГИИ" in user_prompt
    assert "креветки" in user_prompt
    assert "Средиземноморский" in user_prompt
    assert "натрий ≤ 1500" in sys_prompt
    assert "насыщенные жиры ≤ 7" in sys_prompt
    assert "1500" in user_prompt  # sodium cap
    assert "Дневные ориентиры" in user_prompt


def test_system_prompt_for_vegan_pattern() -> None:
    profile = Profile(
        sex=Sex.female,
        age=29,
        weight_kg=58,
        height_cm=168,
        activity=Activity.moderate,
        goal=Goal.maintain,
        diet_pattern=DietPattern.vegan,
    )
    sp = _system_prompt(profile)
    assert "Веган" in sp
    assert "молочка" in sp


def test_system_prompt_for_pregnancy_includes_food_safety() -> None:
    profile = Profile(
        sex=Sex.female,
        age=30,
        weight_kg=70,
        height_cm=170,
        activity=Activity.light,
        goal=Goal.maintain,
        health_flags=frozenset({HealthFlag.pregnancy_t3}),
    )
    sp = _system_prompt(profile)
    assert "сырая рыба" in sp
    assert "алкоголь" in sp.lower()
