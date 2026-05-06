"""Regression tests for HTML escaping of plan / meal text."""

from __future__ import annotations

from nutrition_bot.formatting import format_plan, format_profile
from nutrition_bot.nutrition import (
    Activity,
    Goal,
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
