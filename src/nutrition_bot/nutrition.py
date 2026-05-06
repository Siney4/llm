"""Pure-Python nutrition math: BMR, TDEE, macros, meal distribution.

All formulas are deterministic so they live outside of the LLM. Only meal
*ideas* (creative content) are delegated to the LLM elsewhere.

References:
- Mifflin–St Jeor (1990) — current go-to BMR formula
- PAL (Physical Activity Level) — FAO/WHO 2001, classic Sedentary..Extra grid
"""

from __future__ import annotations

from dataclasses import dataclass
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


PAL: dict[Activity, float] = {
    Activity.sedentary: 1.2,
    Activity.light: 1.375,
    Activity.moderate: 1.55,
    Activity.very: 1.725,
    Activity.extra: 1.9,
}

GOAL_DELTA: dict[Goal, int] = {
    Goal.cut: -500,
    Goal.maintain: 0,
    Goal.bulk: 300,
}

ACTIVITY_LABELS_RU: dict[Activity, str] = {
    Activity.sedentary: "Сидячий — офис, < 5 000 шагов, без тренировок",
    Activity.light: "Лёгкий — 6–8 тыс. шагов, 1–3 лёгкие тренировки/нед",
    Activity.moderate: "Умеренный — 8–10 тыс. шагов, 3–5 тренировок/нед",
    Activity.very: "Высокий — 10–12 тыс. шагов, 6–7 интенсивных тренировок/нед",
    Activity.extra: "Экстремальный — тяжёлый физ. труд + 2 тренировки/день",
}

GOAL_LABELS_RU: dict[Goal, str] = {
    Goal.cut: "Похудение (−500 ккал/сутки)",
    Goal.maintain: "Поддержание веса",
    Goal.bulk: "Набор массы (+300 ккал/сутки)",
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
    """Anthropometric profile + activity + goal."""

    sex: Sex
    age: int
    weight_kg: float
    height_cm: float
    activity: Activity
    goal: Goal

    def __post_init__(self) -> None:
        if not (10 <= self.age <= 100):
            raise ValueError("age must be in [10, 100]")
        if not (30 <= self.weight_kg <= 300):
            raise ValueError("weight_kg must be in [30, 300]")
        if not (120 <= self.height_cm <= 230):
            raise ValueError("height_cm must be in [120, 230]")


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


def bmr_mifflin(profile: Profile) -> float:
    """Mifflin–St Jeor BMR in kcal/day.

    BMR = 10*kg + 6.25*cm − 5*age + s, where s = +5 (m) or −161 (f).
    """
    s = 5.0 if profile.sex is Sex.male else -161.0
    return 10.0 * profile.weight_kg + 6.25 * profile.height_cm - 5.0 * profile.age + s


def tdee(profile: Profile) -> float:
    """Total daily energy expenditure: BMR × PAL."""
    return bmr_mifflin(profile) * PAL[profile.activity]


def target_kcal(profile: Profile) -> int:
    """TDEE adjusted for the user's goal, rounded to nearest 10 kcal."""
    raw = tdee(profile) + GOAL_DELTA[profile.goal]
    return int(round(raw / 10.0)) * 10


def macros(profile: Profile, kcal: int) -> Macros:
    """Compute macros: 2.0 g/kg protein, 1.0 g/kg fat, rest = carbs.

    Carbs are clamped to ≥ 50 g; if protein+fat already exceed kcal target the
    excess is absorbed (we keep protein and fat targets — they're more
    important than hitting the kcal number to the gram).
    """
    protein_g = int(round(profile.weight_kg * 2.0))
    fat_g = int(round(profile.weight_kg * 1.0))
    remaining_kcal = kcal - protein_g * 4 - fat_g * 9
    carbs_g = max(50, int(round(remaining_kcal / 4)))
    return Macros(protein_g=protein_g, fat_g=fat_g, carbs_g=carbs_g)


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
    """Build a complete plan from a user profile."""
    bmr_v = int(round(bmr_mifflin(profile)))
    tdee_v = int(round(tdee(profile)))
    target = target_kcal(profile)
    macros_v = macros(profile, target)
    meals_v, buffer_v = distribute_meals(target, meals_count, buffer_fraction)
    return Plan(
        bmr=bmr_v,
        tdee=tdee_v,
        target_kcal=target,
        macros=macros_v,
        meals=meals_v,
        buffer_kcal=buffer_v,
    )
