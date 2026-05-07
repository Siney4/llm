"""Pure-Python nutrition math: BMR, TDEE, macros, meal distribution.

All formulas are deterministic so they live outside of the LLM. Only meal
*ideas* (creative content) are delegated to the LLM elsewhere.

References:
- Mifflin–St Jeor (1990) — current go-to BMR formula
- PAL (Physical Activity Level) — FAO/WHO 2001, classic Sedentary..Extra grid
- WHO BMI categories (1995) and Ashwell waist-to-height risk thresholds (2012)
- WHO sodium/saturated-fat guidance, ADA carbohydrate ranges for diabetes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Sex(StrEnum):
    male = "male"
    female = "female"


class Activity(StrEnum):
    """Activity level → PAL multiplier (Mifflin–St Jeor classic grid)."""

    sedentary = "sedentary"
    light = "light"
    moderate = "moderate"
    very = "very"
    extra = "extra"


class Goal(StrEnum):
    cut = "cut"
    maintain = "maintain"
    bulk = "bulk"


class GoalPace(StrEnum):
    """How aggressively to chase the goal — scales the kcal delta."""

    slow = "slow"
    standard = "standard"
    aggressive = "aggressive"


class DietPattern(StrEnum):
    """High-level macro pattern. Affects protein/fat/carb split."""

    balanced = "balanced"
    high_protein = "high_protein"
    low_carb = "low_carb"
    mediterranean = "mediterranean"
    vegetarian = "vegetarian"
    vegan = "vegan"


class HealthFlag(StrEnum):
    """Health conditions that nudge calories / macros / sodium / sat fat / fiber."""

    hypertension = "hypertension"
    pre_diabetes = "pre_diabetes"
    diabetes_t2 = "diabetes_t2"
    high_cholesterol = "high_cholesterol"
    kidney_concerns = "kidney_concerns"
    pregnancy_t2 = "pregnancy_t2"
    pregnancy_t3 = "pregnancy_t3"
    breastfeeding = "breastfeeding"


class BmiCategory(StrEnum):
    underweight = "underweight"
    normal = "normal"
    overweight = "overweight"
    obese_1 = "obese_1"
    obese_2 = "obese_2"
    obese_3 = "obese_3"


class WaistRisk(StrEnum):
    low = "low"  # < 0.4 — informational only
    healthy = "healthy"  # 0.4 ≤ r < 0.5
    elevated = "elevated"  # 0.5 ≤ r < 0.6
    high = "high"  # ≥ 0.6


PAL: dict[Activity, float] = {
    Activity.sedentary: 1.2,
    Activity.light: 1.375,
    Activity.moderate: 1.55,
    Activity.very: 1.725,
    Activity.extra: 1.9,
}

# Goal × pace → daily kcal delta (negative = deficit, positive = surplus).
# Standard column matches the historical defaults (-500 / 0 / +300).
GOAL_PACE_DELTA: dict[tuple[Goal, GoalPace], int] = {
    (Goal.cut, GoalPace.slow): -250,
    (Goal.cut, GoalPace.standard): -500,
    (Goal.cut, GoalPace.aggressive): -750,
    (Goal.maintain, GoalPace.slow): 0,
    (Goal.maintain, GoalPace.standard): 0,
    (Goal.maintain, GoalPace.aggressive): 0,
    (Goal.bulk, GoalPace.slow): 200,
    (Goal.bulk, GoalPace.standard): 300,
    (Goal.bulk, GoalPace.aggressive): 500,
}

# Minimum safe daily kcal regardless of deficit aggression. Below this, the
# bot still warns the user to consult a doctor.
KCAL_FLOOR_MALE = 1500
KCAL_FLOOR_FEMALE = 1200

# Pregnancy / lactation kcal additions (WHO/ACOG).
KCAL_ADD_PREGNANCY_T2 = 340
KCAL_ADD_PREGNANCY_T3 = 450
KCAL_ADD_BREASTFEEDING = 500
PROTEIN_ADD_PREGNANCY_G = 25
PROTEIN_ADD_BREASTFEEDING_G = 20

# Diet-pattern → grams of protein per kg body weight (before per-condition caps).
PROTEIN_PER_KG: dict[DietPattern, float] = {
    DietPattern.balanced: 2.0,
    DietPattern.high_protein: 2.4,
    DietPattern.low_carb: 1.8,
    DietPattern.mediterranean: 1.6,
    DietPattern.vegetarian: 1.6,
    DietPattern.vegan: 1.4,
}

# Kidney concerns: cap protein at 1.0 g/kg (KDIGO conservative range for
# non-dialysis CKD; user must still consult a nephrologist).
KIDNEY_PROTEIN_CAP_PER_KG = 1.0


ACTIVITY_LABELS_RU: dict[Activity, str] = {
    Activity.sedentary: "Сидячий — офис, < 5 000 шагов, без тренировок",
    Activity.light: "Лёгкий — 6–8 тыс. шагов, 1–3 лёгкие тренировки/нед",
    Activity.moderate: "Умеренный — 8–10 тыс. шагов, 3–5 тренировок/нед",
    Activity.very: "Высокий — 10–12 тыс. шагов, 6–7 интенсивных тренировок/нед",
    Activity.extra: "Экстремальный — тяжёлый физ. труд + 2 тренировки/день",
}

GOAL_LABELS_RU: dict[Goal, str] = {
    Goal.cut: "Похудение",
    Goal.maintain: "Поддержание веса",
    Goal.bulk: "Набор массы",
}

GOAL_PACE_LABELS_RU: dict[GoalPace, str] = {
    GoalPace.slow: "Мягкий темп (~−250 / +200 ккал)",
    GoalPace.standard: "Стандартный темп (−500 / +300 ккал)",
    GoalPace.aggressive: "Агрессивный темп (−750 / +500 ккал)",
}

DIET_PATTERN_LABELS_RU: dict[DietPattern, str] = {
    DietPattern.balanced: "Сбалансированный (база, 2.0 г/кг белка)",
    DietPattern.high_protein: "Высокобелковый (2.4 г/кг белка)",
    DietPattern.low_carb: "Низкоуглеводный (≤25% ккал из углеводов)",
    DietPattern.mediterranean: "Средиземноморский (35% ккал из жиров)",
    DietPattern.vegetarian: "Вегетарианский (без мяса/рыбы)",
    DietPattern.vegan: "Веганский (без продуктов животного происхождения)",
}

HEALTH_FLAG_LABELS_RU: dict[HealthFlag, str] = {
    HealthFlag.hypertension: "Гипертония / повышенное давление",
    HealthFlag.pre_diabetes: "Пред-диабет",
    HealthFlag.diabetes_t2: "Сахарный диабет 2 типа",
    HealthFlag.high_cholesterol: "Высокий холестерин",
    HealthFlag.kidney_concerns: "Проблемы с почками",
    HealthFlag.pregnancy_t2: "Беременность (2 триместр)",
    HealthFlag.pregnancy_t3: "Беременность (3 триместр)",
    HealthFlag.breastfeeding: "Грудное вскармливание",
}

BMI_CATEGORY_LABELS_RU: dict[BmiCategory, str] = {
    BmiCategory.underweight: "Недостаточный вес",
    BmiCategory.normal: "Норма",
    BmiCategory.overweight: "Избыточный вес",
    BmiCategory.obese_1: "Ожирение 1 ст.",
    BmiCategory.obese_2: "Ожирение 2 ст.",
    BmiCategory.obese_3: "Ожирение 3 ст.",
}

WAIST_RISK_LABELS_RU: dict[WaistRisk, str] = {
    WaistRisk.low: "ниже типичной нормы (информативно)",
    WaistRisk.healthy: "в здоровом диапазоне",
    WaistRisk.elevated: "повышенный риск",
    WaistRisk.high: "высокий метаболический риск",
}

MEAL_LABELS_RU: dict[str, str] = {
    "breakfast": "Завтрак",
    "morning_snack": "Перекус",
    "lunch": "Обед",
    "afternoon_snack": "Перекус",
    "dinner": "Ужин",
    "buffer": "Буфер (вкусняшка / запас)",
}


@dataclass(frozen=True, slots=True)
class Profile:
    """Anthropometric profile + activity + goal + personalisation knobs.

    All new fields default to neutral values so existing call-sites keep
    working: a Profile built from `(sex, age, weight, height, activity, goal)`
    behaves exactly like the previous version did (balanced macros, standard
    pace, no health flags, no allergies, waist unknown).
    """

    sex: Sex
    age: int
    weight_kg: float
    height_cm: float
    activity: Activity
    goal: Goal
    waist_cm: float | None = None
    diet_pattern: DietPattern = DietPattern.balanced
    goal_pace: GoalPace = GoalPace.standard
    health_flags: frozenset[HealthFlag] = field(default_factory=frozenset)
    allergies: str = ""

    def __post_init__(self) -> None:
        if not (10 <= self.age <= 100):
            raise ValueError("age must be in [10, 100]")
        if not (30 <= self.weight_kg <= 300):
            raise ValueError("weight_kg must be in [30, 300]")
        if not (120 <= self.height_cm <= 230):
            raise ValueError("height_cm must be in [120, 230]")
        if self.waist_cm is not None and not (40 <= self.waist_cm <= 200):
            raise ValueError("waist_cm must be in [40, 200] when provided")
        if (
            HealthFlag.pregnancy_t2 in self.health_flags
            and HealthFlag.pregnancy_t3 in self.health_flags
        ):
            raise ValueError("pregnancy_t2 and pregnancy_t3 are mutually exclusive")
        if self.is_pregnant and self.sex is Sex.male:
            raise ValueError("pregnancy flag is incompatible with sex=male")

    @property
    def is_pregnant(self) -> bool:
        return (
            HealthFlag.pregnancy_t2 in self.health_flags
            or HealthFlag.pregnancy_t3 in self.health_flags
        )

    @property
    def has_diabetes_spectrum(self) -> bool:
        return (
            HealthFlag.diabetes_t2 in self.health_flags
            or HealthFlag.pre_diabetes in self.health_flags
        )


@dataclass(frozen=True, slots=True)
class Macros:
    """Macronutrient breakdown in grams (and derived kcal)."""

    protein_g: int
    fat_g: int
    carbs_g: int

    @property
    def kcal(self) -> int:
        # 4 kcal/g protein, 9 kcal/g fat, 4 kcal/g carbs.
        return self.protein_g * 4 + self.fat_g * 9 + self.carbs_g * 4


@dataclass(frozen=True, slots=True)
class Meal:
    """A single meal slot with its kcal target."""

    key: str
    label: str
    kcal: int


@dataclass(frozen=True, slots=True)
class Plan:
    bmr: int
    tdee: int
    target_kcal: int
    macros: Macros
    meals: tuple[Meal, ...]
    buffer_kcal: int
    bmi: float
    bmi_category: BmiCategory
    waist_to_height: float | None
    waist_risk: WaistRisk | None
    hydration_l: float
    fiber_g: int
    saturated_fat_cap_g: int
    sodium_cap_mg: int
    warnings: tuple[str, ...]


def bmr_mifflin(profile: Profile) -> float:
    """Mifflin–St Jeor BMR in kcal/day.

    BMR = 10*kg + 6.25*cm − 5*age + s, where s = +5 (m) or −161 (f).
    """
    s = 5.0 if profile.sex is Sex.male else -161.0
    return 10.0 * profile.weight_kg + 6.25 * profile.height_cm - 5.0 * profile.age + s


def tdee(profile: Profile) -> float:
    """Total daily energy expenditure: BMR × PAL."""
    return bmr_mifflin(profile) * PAL[profile.activity]


def kcal_floor(profile: Profile) -> int:
    """Minimum safe daily kcal (sex-specific)."""
    return KCAL_FLOOR_MALE if profile.sex is Sex.male else KCAL_FLOOR_FEMALE


def target_kcal(profile: Profile) -> int:
    """TDEE adjusted for the user's goal/pace, plus pregnancy/lactation,
    clamped to the safety floor and rounded to the nearest 10 kcal."""
    delta = GOAL_PACE_DELTA[(profile.goal, profile.goal_pace)]
    raw = tdee(profile) + delta
    if HealthFlag.pregnancy_t2 in profile.health_flags:
        raw += KCAL_ADD_PREGNANCY_T2
    elif HealthFlag.pregnancy_t3 in profile.health_flags:
        raw += KCAL_ADD_PREGNANCY_T3
    if HealthFlag.breastfeeding in profile.health_flags:
        raw += KCAL_ADD_BREASTFEEDING
    raw = max(raw, float(kcal_floor(profile)))
    return int(round(raw / 10.0)) * 10


def _protein_g(profile: Profile) -> int:
    """Protein target in grams: pattern-based, capped for kidney issues,
    bumped for pregnancy / breastfeeding."""
    per_kg = PROTEIN_PER_KG[profile.diet_pattern]
    if HealthFlag.kidney_concerns in profile.health_flags:
        per_kg = min(per_kg, KIDNEY_PROTEIN_CAP_PER_KG)
    grams = profile.weight_kg * per_kg
    if profile.is_pregnant:
        grams += PROTEIN_ADD_PREGNANCY_G
    if HealthFlag.breastfeeding in profile.health_flags:
        grams += PROTEIN_ADD_BREASTFEEDING_G
    return int(round(grams))


def _carb_cap_kcal_fraction(profile: Profile) -> float | None:
    """Maximum share of kcal from carbs, if the diet pattern / health flags
    impose one. Returns None when there's no cap (carbs absorb the remainder)."""
    if profile.diet_pattern is DietPattern.low_carb:
        # ADA: 20% kcal carbs is consistent with very-low-carb advice for diabetes.
        return 0.20 if profile.has_diabetes_spectrum else 0.25
    if profile.has_diabetes_spectrum:
        # Liberal-low for diabetes/pre-diabetes outside an explicitly low-carb plan.
        return 0.30
    return None


def macros(profile: Profile, kcal: int) -> Macros:
    """Compute macros in grams given a daily kcal target.

    The split depends on the user's `diet_pattern` and `health_flags`:

    - Protein: from `PROTEIN_PER_KG[pattern]`, capped at 1.0 g/kg for kidney
      concerns, bumped by +25 g during pregnancy and +20 g while breastfeeding.
    - Fat: per-pattern target (`weight × ratio` for balanced/protein/vegetarian/
      vegan; ~35% kcal for mediterranean; "fills the rest" for low-carb).
    - Carbs: usually fill the remainder; capped to a kcal share when the user
      has diabetes/pre-diabetes or chose a low-carb pattern.

    Carbs floor at 50 g/day (brain glucose minimum); fat floor at 30 g/day so
    pathological combinations (e.g. very-low kcal with low-carb pattern) still
    return a sane macro mix.
    """
    pattern = profile.diet_pattern
    weight = profile.weight_kg
    protein_g = _protein_g(profile)
    cap_frac = _carb_cap_kcal_fraction(profile)

    if pattern is DietPattern.low_carb:
        carbs_g = max(50, int(round(kcal * (cap_frac or 0.25) / 4)))
        fat_kcal = kcal - protein_g * 4 - carbs_g * 4
        fat_g = max(40, int(round(fat_kcal / 9)))
    elif pattern is DietPattern.mediterranean:
        fat_g = int(round(kcal * 0.35 / 9))
        carb_kcal = kcal - protein_g * 4 - fat_g * 9
        if cap_frac is not None:
            carbs_g = max(50, min(int(round(kcal * cap_frac / 4)), int(round(carb_kcal / 4))))
        else:
            carbs_g = max(50, int(round(carb_kcal / 4)))
    else:
        # balanced / high_protein / vegetarian / vegan
        fat_per_kg = 0.9 if pattern is DietPattern.vegan else 1.0
        fat_g = max(30, int(round(weight * fat_per_kg)))
        carb_kcal = kcal - protein_g * 4 - fat_g * 9
        if cap_frac is not None:
            carbs_g = max(50, min(int(round(kcal * cap_frac / 4)), int(round(carb_kcal / 4))))
        else:
            carbs_g = max(50, int(round(carb_kcal / 4)))

    return Macros(protein_g=protein_g, fat_g=fat_g, carbs_g=carbs_g)


def bmi(profile: Profile) -> float:
    """Body Mass Index in kg/m²."""
    h_m = profile.height_cm / 100.0
    return profile.weight_kg / (h_m * h_m)


def bmi_category(value: float) -> BmiCategory:
    """WHO BMI categorisation."""
    if value < 18.5:
        return BmiCategory.underweight
    if value < 25.0:
        return BmiCategory.normal
    if value < 30.0:
        return BmiCategory.overweight
    if value < 35.0:
        return BmiCategory.obese_1
    if value < 40.0:
        return BmiCategory.obese_2
    return BmiCategory.obese_3


def waist_to_height(profile: Profile) -> float | None:
    """Waist-to-height ratio (Ashwell): better predictor of cardiometabolic
    risk than BMI. Returns None when waist isn't provided."""
    if profile.waist_cm is None:
        return None
    return profile.waist_cm / profile.height_cm


def waist_risk(ratio: float) -> WaistRisk:
    if ratio < 0.4:
        return WaistRisk.low
    if ratio < 0.5:
        return WaistRisk.healthy
    if ratio < 0.6:
        return WaistRisk.elevated
    return WaistRisk.high


def hydration_target_l(profile: Profile) -> float:
    """Roughly 30 ml/kg with a +500 ml/day bump for very/extra activity to
    cover sweat losses. Output in litres, 1 decimal."""
    base_ml = profile.weight_kg * 30.0
    if profile.activity in (Activity.very, Activity.extra):
        base_ml += 500.0
    return round(base_ml / 1000.0, 1)


def fiber_target_g(daily_kcal: int, has_diabetes_spectrum: bool = False) -> int:
    """USDA / Dietary Guidelines: ~14 g fiber per 1000 kcal, ≥35 g for diabetes."""
    base = int(round(daily_kcal / 1000.0 * 14.0))
    return max(base, 35) if has_diabetes_spectrum else base


def saturated_fat_cap_g(daily_kcal: int, has_high_cholesterol: bool = False) -> int:
    """WHO: <10% kcal from saturated fat; AHA: <7% for high cholesterol."""
    pct = 0.07 if has_high_cholesterol else 0.10
    return int(round(daily_kcal * pct / 9.0))


def sodium_cap_mg(has_hypertension: bool = False) -> int:
    """WHO ≤2300 mg/day; AHA ≤1500 mg/day with hypertension."""
    return 1500 if has_hypertension else 2300


def _build_warnings(
    profile: Profile,
    cat: BmiCategory,
    wrisk: WaistRisk | None,
    daily_kcal: int,
) -> tuple[str, ...]:
    """Health-aware nudges shown above the plan. Always non-medical advice."""
    out: list[str] = []
    if HealthFlag.kidney_concerns in profile.health_flags:
        out.append("Почки: обязательно согласуй план с нефрологом. Белок ограничен до 1.0 г/кг.")
    if profile.is_pregnant:
        out.append(
            "Беременность: план только под наблюдением акушера-гинеколога. "
            "Добавлены +340/+450 ккал и +25 г белка."
        )
    if HealthFlag.breastfeeding in profile.health_flags:
        out.append("Грудное вскармливание: добавлены +500 ккал и +20 г белка.")
    if HealthFlag.diabetes_t2 in profile.health_flags:
        out.append(
            "СД 2 типа: следи за гликемией, корректируй план с эндокринологом. "
            "Углеводы ограничены ≤30% ккал."
        )
    elif HealthFlag.pre_diabetes in profile.health_flags:
        out.append("Пред-диабет: углеводы ограничены ≤30% ккал, упор на клетчатку.")
    if HealthFlag.hypertension in profile.health_flags:
        out.append("Гипертония: натрий ≤1500 мг/сутки, упор на овощи (DASH-стиль).")
    if HealthFlag.high_cholesterol in profile.health_flags:
        out.append(
            "Высокий холестерин: насыщенные жиры ≤7% ккал, приоритет — рыба и моно-ненасыщенные."
        )
    if cat in (BmiCategory.obese_2, BmiCategory.obese_3):
        out.append("ИМТ ≥ 35: настоятельно рекомендую начать с консультации врача.")
    if cat is BmiCategory.underweight and profile.goal is Goal.cut:
        out.append("ИМТ < 18.5 — дефицит калорий не показан, цель пересмотрена.")
    if wrisk is WaistRisk.high:
        out.append(
            "Талия / рост ≥ 0.6 — высокий метаболический риск, "
            "приоритет — снижение абдоминального жира."
        )
    raw_target = tdee(profile) + GOAL_PACE_DELTA[(profile.goal, profile.goal_pace)]
    if raw_target < kcal_floor(profile):
        out.append(
            f"Расчётный калораж ниже безопасного минимума ({kcal_floor(profile)} ккал) "
            "— план поднят до пола, дефицит будет мягче запрошенного."
        )
    return tuple(out)


# Distribution profiles per meal count. Sums to 1.0 (validated below).
# Order matters — it's the order of keys in `_MEAL_KEYS`.
_DISTRIBUTIONS: dict[int, tuple[float, ...]] = {
    3: (0.30, 0.40, 0.30),
    # B / L / afternoon snack / D — main meals stay big, snack is the lightest slot.
    4: (0.25, 0.35, 0.15, 0.25),
    5: (0.25, 0.10, 0.30, 0.10, 0.25),
}

_MEAL_KEYS: dict[int, tuple[str, ...]] = {
    3: ("breakfast", "lunch", "dinner"),
    4: ("breakfast", "lunch", "afternoon_snack", "dinner"),
    5: ("breakfast", "morning_snack", "lunch", "afternoon_snack", "dinner"),
}


def _validate_distribution() -> None:
    for n, dist in _DISTRIBUTIONS.items():
        if len(dist) != n:
            raise AssertionError(f"distribution for {n} meals has length {len(dist)}")
        if abs(sum(dist) - 1.0) > 1e-6:
            raise AssertionError(f"distribution for {n} meals sums to {sum(dist)} ≠ 1.0")
        if len(_MEAL_KEYS[n]) != n:
            raise AssertionError(f"meal keys for {n} meals has wrong length")


_validate_distribution()


def distribute_meals(
    target_kcal_value: int,
    meals_count: int,
    buffer_fraction: float = 0.15,
) -> tuple[tuple[Meal, ...], int]:
    """Split target kcal across N meals + a "buffer" slot for treats / surprises.

    Returns ``(meals, buffer_kcal)``. Sum of meals + buffer == target_kcal_value
    (rounding errors land in the buffer so the day always closes exactly).

    - ``meals_count`` must be 3, 4 or 5
    - ``buffer_fraction`` is the share of TDEE reserved for the 80/20 rule
      (default 15%, configurable via env). 0 disables the buffer.
    """
    if meals_count not in _DISTRIBUTIONS:
        raise ValueError(f"meals_count must be one of {sorted(_DISTRIBUTIONS)}")
    if not (0.0 <= buffer_fraction <= 0.4):
        raise ValueError("buffer_fraction must be in [0.0, 0.4]")

    buffer_kcal = int(round(target_kcal_value * buffer_fraction / 10.0)) * 10
    meals_budget = target_kcal_value - buffer_kcal

    dist = _DISTRIBUTIONS[meals_count]
    keys = _MEAL_KEYS[meals_count]

    # Round each share to nearest 10 kcal, then absorb the rounding remainder
    # into the buffer so the total is exact. If the buffer would go negative
    # (possible when buffer_fraction is 0 or tiny), fold the drift into the
    # largest meal slot instead — keeps the invariant `sum(meals)+buffer ==
    # target` and never produces a negative buffer.
    raw = [int(round(meals_budget * frac / 10.0)) * 10 for frac in dist]
    rounding_drift = meals_budget - sum(raw)
    if buffer_kcal + rounding_drift >= 0:
        buffer_kcal += rounding_drift
    else:
        max_idx = max(range(len(raw)), key=lambda i: raw[i])
        raw[max_idx] += rounding_drift

    meals = tuple(
        Meal(key=k, label=MEAL_LABELS_RU[k], kcal=kc) for k, kc in zip(keys, raw, strict=True)
    )
    return meals, buffer_kcal


def build_plan(profile: Profile, meals_count: int, buffer_fraction: float = 0.15) -> Plan:
    """Build a complete plan from a user profile.

    All derived health metrics (BMI, waist-to-height, hydration, fiber,
    saturated fat / sodium caps, warnings) are computed here so the
    formatting layer just renders them.
    """
    bmr_v = int(round(bmr_mifflin(profile)))
    tdee_v = int(round(tdee(profile)))
    target = target_kcal(profile)
    macros_v = macros(profile, target)
    meals_v, buffer_v = distribute_meals(target, meals_count, buffer_fraction)

    bmi_v = bmi(profile)
    cat = bmi_category(bmi_v)
    wth = waist_to_height(profile)
    wrisk = waist_risk(wth) if wth is not None else None

    return Plan(
        bmr=bmr_v,
        tdee=tdee_v,
        target_kcal=target,
        macros=macros_v,
        meals=meals_v,
        buffer_kcal=buffer_v,
        bmi=bmi_v,
        bmi_category=cat,
        waist_to_height=wth,
        waist_risk=wrisk,
        hydration_l=hydration_target_l(profile),
        fiber_g=fiber_target_g(target, profile.has_diabetes_spectrum),
        saturated_fat_cap_g=saturated_fat_cap_g(
            target, HealthFlag.high_cholesterol in profile.health_flags
        ),
        sodium_cap_mg=sodium_cap_mg(HealthFlag.hypertension in profile.health_flags),
        warnings=_build_warnings(profile, cat, wrisk, target),
    )


# Backwards-compatible re-export: the legacy GOAL_DELTA mapping (used by some
# imports / docs) is now derivable from GOAL_PACE_DELTA[(g, GoalPace.standard)].
GOAL_DELTA: dict[Goal, int] = {g: GOAL_PACE_DELTA[(g, GoalPace.standard)] for g in Goal}
