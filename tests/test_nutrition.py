"""Unit tests for the deterministic nutrition math."""

from __future__ import annotations

import pytest

from nutrition_bot.nutrition import (
    Activity,
    BmiCategory,
    DietPattern,
    Goal,
    GoalPace,
    HealthFlag,
    Profile,
    Sex,
    WaistRisk,
    bmi,
    bmi_category,
    bmr_mifflin,
    build_plan,
    distribute_meals,
    fiber_target_g,
    hydration_target_l,
    macros,
    saturated_fat_cap_g,
    sodium_cap_mg,
    target_kcal,
    tdee,
    waist_risk,
    waist_to_height,
)


def make(
    sex: Sex = Sex.male,
    age: int = 30,
    weight: float = 80,
    height: float = 180,
    activity: Activity = Activity.moderate,
    goal: Goal = Goal.maintain,
    waist_cm: float | None = None,
    diet_pattern: DietPattern = DietPattern.balanced,
    goal_pace: GoalPace = GoalPace.standard,
    health_flags: frozenset[HealthFlag] = frozenset(),
    allergies: str = "",
) -> Profile:
    return Profile(
        sex=sex,
        age=age,
        weight_kg=weight,
        height_cm=height,
        activity=activity,
        goal=goal,
        waist_cm=waist_cm,
        diet_pattern=diet_pattern,
        goal_pace=goal_pace,
        health_flags=health_flags,
        allergies=allergies,
    )


# ---------------------------------------------------------------- BMR / TDEE


def test_bmr_male_reference() -> None:
    """Reference: 30y, 80kg, 180cm male → BMR ≈ 1780 (Mifflin–St Jeor)."""
    p = make()
    assert round(bmr_mifflin(p)) == 1780


def test_bmr_female_reference() -> None:
    """30y/60kg/165cm female → BMR = 600 + 1031.25 − 150 − 161 = 1320.25."""
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


# ---------------------------------------------------------------- Goal & pace


def test_target_kcal_goal_delta() -> None:
    """Default pace=standard reproduces the historical -500 / +300 deltas."""
    base = make()
    cut = make(goal=Goal.cut)
    bulk = make(goal=Goal.bulk)
    assert target_kcal(cut) == target_kcal(base) - 500
    assert target_kcal(bulk) == target_kcal(base) + 300


def test_target_kcal_pace_scales_delta() -> None:
    p_slow = make(goal=Goal.cut, goal_pace=GoalPace.slow)
    p_std = make(goal=Goal.cut, goal_pace=GoalPace.standard)
    p_aggr = make(goal=Goal.cut, goal_pace=GoalPace.aggressive)
    base = target_kcal(make(goal=Goal.maintain))
    assert target_kcal(p_slow) == base - 250
    assert target_kcal(p_std) == base - 500
    assert target_kcal(p_aggr) == base - 750


def test_target_kcal_rounded_to_10() -> None:
    p = make()
    assert target_kcal(p) % 10 == 0


def test_kcal_floor_protects_aggressive_female_cut() -> None:
    """Tiny sedentary female with aggressive cut would otherwise sink below
    the safety floor — the floor must clamp to 1200 kcal."""
    p = make(
        sex=Sex.female,
        weight=50,
        height=160,
        age=40,
        activity=Activity.sedentary,
        goal=Goal.cut,
        goal_pace=GoalPace.aggressive,
    )
    assert target_kcal(p) == 1200


def test_kcal_floor_protects_aggressive_male_cut() -> None:
    p = make(
        weight=60,
        height=170,
        age=50,
        activity=Activity.sedentary,
        goal=Goal.cut,
        goal_pace=GoalPace.aggressive,
    )
    assert target_kcal(p) == 1500


def test_pregnancy_adds_kcal_and_protein() -> None:
    base = make(sex=Sex.female, weight=65, height=170, age=30)
    preg_t2 = make(
        sex=Sex.female,
        weight=65,
        height=170,
        age=30,
        health_flags=frozenset({HealthFlag.pregnancy_t2}),
    )
    preg_t3 = make(
        sex=Sex.female,
        weight=65,
        height=170,
        age=30,
        health_flags=frozenset({HealthFlag.pregnancy_t3}),
    )
    assert target_kcal(preg_t2) == target_kcal(base) + 340
    assert target_kcal(preg_t3) == target_kcal(base) + 450
    base_p = macros(base, target_kcal(base)).protein_g
    preg_p = macros(preg_t2, target_kcal(preg_t2)).protein_g
    assert preg_p >= base_p + 25


def test_breastfeeding_adds_kcal_and_protein() -> None:
    base = make(sex=Sex.female, weight=65, height=170, age=30)
    bf = make(
        sex=Sex.female,
        weight=65,
        height=170,
        age=30,
        health_flags=frozenset({HealthFlag.breastfeeding}),
    )
    assert target_kcal(bf) == target_kcal(base) + 500
    base_p = macros(base, target_kcal(base)).protein_g
    bf_p = macros(bf, target_kcal(bf)).protein_g
    assert bf_p >= base_p + 20


def test_pregnancy_male_rejected() -> None:
    with pytest.raises(ValueError):
        make(health_flags=frozenset({HealthFlag.pregnancy_t2}))


def test_pregnancy_trimesters_mutually_exclusive() -> None:
    with pytest.raises(ValueError):
        make(
            sex=Sex.female,
            weight=65,
            height=170,
            health_flags=frozenset({HealthFlag.pregnancy_t2, HealthFlag.pregnancy_t3}),
        )


# ---------------------------------------------------------------- Macros


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


def test_macros_high_protein_pattern_bumps_protein() -> None:
    p_bal = make(weight=80, diet_pattern=DietPattern.balanced)
    p_hp = make(weight=80, diet_pattern=DietPattern.high_protein)
    assert macros(p_hp, 2400).protein_g > macros(p_bal, 2400).protein_g
    assert macros(p_hp, 2400).protein_g == pytest.approx(80 * 2.4, abs=1)


def test_macros_low_carb_caps_carbs() -> None:
    p = make(weight=80, diet_pattern=DietPattern.low_carb)
    m = macros(p, 2400)
    # ≤25% of 2400 kcal from carbs → ≤150 g.
    assert m.carbs_g <= 155


def test_macros_mediterranean_targets_35pct_fat() -> None:
    p = make(weight=80, diet_pattern=DietPattern.mediterranean)
    m = macros(p, 2400)
    expected_fat_g = round(2400 * 0.35 / 9)
    assert m.fat_g == pytest.approx(expected_fat_g, abs=1)


def test_macros_kidney_caps_protein_at_1g_per_kg() -> None:
    p = make(weight=80, health_flags=frozenset({HealthFlag.kidney_concerns}))
    m = macros(p, 2400)
    assert m.protein_g == pytest.approx(80, abs=1)


def test_macros_diabetes_caps_carbs_at_30pct() -> None:
    p = make(weight=80, health_flags=frozenset({HealthFlag.diabetes_t2}))
    m = macros(p, 2400)
    # 30% of 2400 / 4 = 180 g
    assert m.carbs_g <= 185


def test_macros_vegan_lower_protein_and_fat() -> None:
    p = make(weight=80, diet_pattern=DietPattern.vegan)
    m = macros(p, 2400)
    assert m.protein_g == pytest.approx(80 * 1.4, abs=1)
    assert m.fat_g == pytest.approx(80 * 0.9, abs=1)


# ---------------------------------------------------------------- BMI / waist


@pytest.mark.parametrize(
    ("weight", "height", "expected_cat"),
    [
        (45, 170, BmiCategory.underweight),
        (60, 170, BmiCategory.normal),
        (80, 170, BmiCategory.overweight),
        (95, 170, BmiCategory.obese_1),
        (105, 170, BmiCategory.obese_2),
        (130, 170, BmiCategory.obese_3),
    ],
)
def test_bmi_categorisation(weight: float, height: float, expected_cat: BmiCategory) -> None:
    p = make(weight=weight, height=height)
    assert bmi_category(bmi(p)) is expected_cat


@pytest.mark.parametrize(
    ("waist", "height", "expected"),
    [
        (60, 170, WaistRisk.low),
        (70, 170, WaistRisk.healthy),
        (90, 170, WaistRisk.elevated),
        (110, 170, WaistRisk.high),
    ],
)
def test_waist_risk_thresholds(waist: float, height: float, expected: WaistRisk) -> None:
    p = make(weight=80, height=height, waist_cm=waist)
    ratio = waist_to_height(p)
    assert ratio is not None
    assert waist_risk(ratio) is expected


def test_waist_to_height_none_when_unset() -> None:
    p = make()
    assert waist_to_height(p) is None


# ---------------------------------------------------------------- Hydration / fiber / caps


def test_hydration_baseline_30ml_per_kg() -> None:
    p = make(weight=80, activity=Activity.sedentary)
    assert hydration_target_l(p) == pytest.approx(2.4, abs=0.05)


def test_hydration_active_bumps_500ml() -> None:
    p_low = make(weight=80, activity=Activity.light)
    p_high = make(weight=80, activity=Activity.very)
    assert hydration_target_l(p_high) > hydration_target_l(p_low)


def test_fiber_baseline_14g_per_1000kcal() -> None:
    assert fiber_target_g(2000) == 28
    assert fiber_target_g(2500) == 35


def test_fiber_diabetes_minimum_35g() -> None:
    assert fiber_target_g(1800, has_diabetes_spectrum=True) == 35


def test_sat_fat_cap_default_10pct() -> None:
    # 2000 * 0.10 / 9 ≈ 22 g
    assert saturated_fat_cap_g(2000) == pytest.approx(22, abs=1)


def test_sat_fat_cap_high_chol_drops_to_7pct() -> None:
    assert saturated_fat_cap_g(2000, has_high_cholesterol=True) == pytest.approx(16, abs=1)


def test_sodium_cap_hypertension_drops_to_1500() -> None:
    assert sodium_cap_mg(False) == 2300
    assert sodium_cap_mg(True) == 1500


# ---------------------------------------------------------------- Distribution


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


# ---------------------------------------------------------------- Plan integration


def test_build_plan_full() -> None:
    p = make()
    plan = build_plan(p, meals_count=4, buffer_fraction=0.15)
    assert plan.bmr == 1780
    assert plan.tdee == 2759
    assert plan.target_kcal == 2760
    assert sum(m.kcal for m in plan.meals) + plan.buffer_kcal == plan.target_kcal
    assert len(plan.meals) == 4
    # New extras present and sane.
    assert plan.bmi == pytest.approx(80 / (1.8**2), abs=0.1)
    assert plan.waist_to_height is None
    assert plan.hydration_l == pytest.approx(2.4, abs=0.1)
    assert plan.sodium_cap_mg == 2300
    assert plan.warnings == ()


def test_build_plan_warnings_for_kidney() -> None:
    p = make(health_flags=frozenset({HealthFlag.kidney_concerns}))
    plan = build_plan(p, meals_count=3)
    assert any("Почки" in w for w in plan.warnings)


def test_build_plan_warnings_for_pregnancy() -> None:
    p = make(
        sex=Sex.female,
        weight=70,
        height=170,
        health_flags=frozenset({HealthFlag.pregnancy_t3}),
    )
    plan = build_plan(p, meals_count=3)
    assert any("Беременность" in w for w in plan.warnings)


def test_build_plan_warnings_for_obese_2_plus() -> None:
    p = make(weight=120, height=170)
    plan = build_plan(p, meals_count=3)
    assert any("ИМТ ≥ 35" in w for w in plan.warnings)


def test_build_plan_warnings_for_high_waist() -> None:
    p = make(waist_cm=110, height=170)
    plan = build_plan(p, meals_count=3)
    assert any("Талия / рост" in w for w in plan.warnings)


def test_build_plan_warnings_for_aggressive_floor() -> None:
    p = make(
        sex=Sex.female,
        weight=50,
        height=160,
        age=40,
        activity=Activity.sedentary,
        goal=Goal.cut,
        goal_pace=GoalPace.aggressive,
    )
    plan = build_plan(p, meals_count=3)
    assert plan.target_kcal == 1200
    assert any("безопасного минимума" in w for w in plan.warnings)


# ---------------------------------------------------------------- Validation


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


def test_profile_validation_rejects_bad_waist() -> None:
    with pytest.raises(ValueError):
        make(waist_cm=10)
    with pytest.raises(ValueError):
        make(waist_cm=300)
