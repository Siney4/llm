"""Regression tests for HTML escaping of plan / meal text."""

from __future__ import annotations

from nutrition_bot.formatting import format_plan, format_profile
from nutrition_bot.nutrition import (
    Activity,
    DietPattern,
    Goal,
    HealthFlag,
    Profile,
    Sex,
    build_plan,
)


def test_format_profile_escapes_sedentary_label() -> None:
    """Sedentary label contains '< 5 000 шагов' — must come out HTML-escaped."""
    p = Profile(
        sex=Sex.male,
        age=30,
        weight_kg=80,
        height_cm=180,
        activity=Activity.sedentary,
        goal=Goal.maintain,
    )
    text = format_profile(p)
    # Raw '<' followed by space is what would break Telegram HTML parsing.
    assert "< " not in text
    assert "&lt; 5\xa0000" in text or "&lt; 5 000" in text


def test_format_plan_renders_for_each_activity() -> None:
    """Smoke check: format_plan never produces a stray bare '<' in user-facing text."""
    for act in Activity:
        for goal in Goal:
            p = Profile(
                sex=Sex.female,
                age=25,
                weight_kg=60,
                height_cm=165,
                activity=act,
                goal=goal,
            )
            plan = build_plan(p, meals_count=4, buffer_fraction=0.15)
            text = format_plan(p, plan)
            # Every '<' must be the start of an allowed tag (<b>, </b>) — no naked '< ' sequences.
            assert "< " not in text
            assert "<b>" in text  # bold tags survive escaping


def test_format_plan_escapes_user_supplied_allergies() -> None:
    """A wildly typed allergies field must come out HTML-escaped."""
    p = Profile(
        sex=Sex.female,
        age=29,
        weight_kg=58,
        height_cm=168,
        activity=Activity.light,
        goal=Goal.maintain,
        diet_pattern=DietPattern.vegan,
        allergies="<script>alert(1)</script> & орехи",
    )
    plan = build_plan(p, meals_count=3)
    text = format_plan(p, plan)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&amp; орехи" in text


def test_format_plan_includes_warnings_for_kidney() -> None:
    p = Profile(
        sex=Sex.male,
        age=55,
        weight_kg=82,
        height_cm=178,
        activity=Activity.light,
        goal=Goal.maintain,
        health_flags=frozenset({HealthFlag.kidney_concerns}),
    )
    plan = build_plan(p, meals_count=3)
    text = format_plan(p, plan)
    assert "Почки" in text
    assert "<b>Важно:</b>" in text or "Важно" in text
