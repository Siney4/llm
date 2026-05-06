"""Unit tests for the deterministic nutrition math."""

from __future__ import annotations

import pytest

from nutrition_bot.nutrition import (
    Activity,
    Goal,
    Profile,
    Sex,
    bmr_mifflin,
    build_plan,
    distribute_meals,
    macros,
    target_kcal,
    tdee,
)


def make(
    sex: Sex = Sex.male,
    age: int = 30,
    weight: float = 80,
    height: float = 180,
    activity: Activity = Activity.moderate,
    goal: Goal = Goal.maintain,
) -> Profile:
    return Profile(
        sex=sex,
        age=age,
        weight_kg=weight,
        height_cm=height,
        activity=activity,
        goal=goal,
    )


def test_bmr_male_reference() -> None:
    """Reference: 30y, 80kg, 180cm male → BMR ≈ 1780 (Mifflin–St Jeor)."""
    p = make()
    assert round(bmr_mifflin(p)) == 1780


def test_bmr_female_reference() -> None:
    """30y/60kg/165cm female → BMR = 600 + 1031.25 − 150 − 161 = 1320.25 (Mifflin–St Jeor)."""
    p = make(sex=Sex.female, weight=60, height=165)
    assert round(bmr_mifflin(p)) == 1320


@pytest.mark.parametrize(
    ("activity", "expected_tdee"),
    [
        (Activity.sedentary, 2136),
        (Activity.light, 2447),
        (Activity.moderate, 2759),
        (Activity.very, 3070),
        (Activity.extra, 3382),
    ],
)
def test_tdee_matches_pal_table(activity: Activity, expected_tdee: int) -> None:
    """30y/80kg/180cm male × PAL grid — values from the user's reference table."""
    p = make(activity=activity)
    assert round(tdee(p)) == pytest.approx(expected_tdee, abs=1)


def test_target_kcal_goal_delta() -> None:
    base = make()
    cut = make(goal=Goal.cut)
    bulk = make(goal=Goal.bulk)
    assert target_kcal(cut) == target_kcal(base) - 500
    assert target_kcal(bulk) == target_kcal(base) + 300


def test_target_kcal_rounded_to_10() -> None:
    p = make()
    assert target_kcal(p) % 10 == 0


def test_macros_protein_and_fat_per_kg() -> None:
    p = make(weight=80)
    m = macros(p, 2400)
    assert m.protein_g == 160  # 2.0 g/kg × 80
    assert m.fat_g == 80  # 1.0 g/kg × 80


def test_macros_carbs_close_to_remaining_kcal() -> None:
    p = make(weight=80)
    m = macros(p, 2400)
    # 160*4 + 80*9 = 640 + 720 = 1360. Remaining 1040 → carbs ≈ 260 g.
    assert m.carbs_g == pytest.approx(260, abs=1)


def test_distribute_meals_3() -> None:
    meals, buf = distribute_meals(2400, 3, buffer_fraction=0.15)
    assert len(meals) == 3
    assert sum(m.kcal for m in meals) + buf == 2400
    assert buf > 0
    # Buffer should be roughly 15% of total.
    assert 300 <= buf <= 400


def test_distribute_meals_4() -> None:
    meals, buf = distribute_meals(2400, 4, buffer_fraction=0.15)
    assert len(meals) == 4
    assert sum(m.kcal for m in meals) + buf == 2400
    keys = [m.key for m in meals]
    assert keys == ["breakfast", "lunch", "afternoon_snack", "dinner"]
    # Snack must be the smallest slot; main meals stay biggest.
    by_key = {m.key: m.kcal for m in meals}
    assert by_key["afternoon_snack"] < by_key["breakfast"]
    assert by_key["afternoon_snack"] < by_key["lunch"]
    assert by_key["afternoon_snack"] < by_key["dinner"]
    assert by_key["lunch"] >= by_key["breakfast"]
    assert by_key["lunch"] >= by_key["dinner"]


def test_distribute_meals_5() -> None:
    meals, buf = distribute_meals(2400, 5, buffer_fraction=0.10)
    assert len(meals) == 5
    assert sum(m.kcal for m in meals) + buf == 2400
    assert 200 <= buf <= 280


def test_distribute_meals_zero_buffer() -> None:
    meals, buf = distribute_meals(2000, 3, buffer_fraction=0.0)
    assert buf == 0
    assert sum(m.kcal for m in meals) == 2000


def test_distribute_meals_zero_buffer_with_drift() -> None:
    """When buffer_fraction=0 and rounding overshoots, buffer must stay ≥ 0
    and the day still closes exactly (drift folded into largest meal)."""
    # 5 meals + target=2070 → meals overshoot meals_budget by 10.
    meals, buf = distribute_meals(2070, 5, buffer_fraction=0.0)
    assert buf >= 0
    assert sum(m.kcal for m in meals) + buf == 2070


@pytest.mark.parametrize("target", [1500, 1810, 2070, 2200, 2430, 2615, 2890])
@pytest.mark.parametrize("count", [3, 4, 5])
@pytest.mark.parametrize("frac", [0.0, 0.05, 0.10, 0.15, 0.20])
def test_distribute_meals_invariant_holds(target: int, count: int, frac: float) -> None:
    """sum(meals) + buffer == target, buffer ≥ 0, every meal > 0 — across the grid."""
    meals, buf = distribute_meals(target, count, buffer_fraction=frac)
    assert buf >= 0
    assert sum(m.kcal for m in meals) + buf == target
    assert all(m.kcal > 0 for m in meals)


def test_distribute_meals_invalid_count() -> None:
    with pytest.raises(ValueError):
        distribute_meals(2000, 6)


def test_distribute_meals_invalid_buffer() -> None:
    with pytest.raises(ValueError):
        distribute_meals(2000, 3, buffer_fraction=0.6)


def test_build_plan_full() -> None:
    p = make()
    plan = build_plan(p, meals_count=4, buffer_fraction=0.15)
    assert plan.bmr == 1780
    assert plan.tdee == 2759
    # No goal delta → target == TDEE rounded to 10.
    assert plan.target_kcal == 2760
    assert sum(m.kcal for m in plan.meals) + plan.buffer_kcal == plan.target_kcal
    assert len(plan.meals) == 4


def test_profile_validation_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        Profile(
            sex=Sex.male,
            age=5,
            weight_kg=80,
            height_cm=180,
            activity=Activity.moderate,
            goal=Goal.maintain,
        )
    with pytest.raises(ValueError):
        Profile(
            sex=Sex.male,
            age=30,
            weight_kg=10,
            height_cm=180,
            activity=Activity.moderate,
            goal=Goal.maintain,
        )
