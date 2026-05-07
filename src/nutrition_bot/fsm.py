"""FSM states for the onboarding questionnaire."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    sex = State()
    age = State()
    weight = State()
    height = State()
    waist = State()
    activity = State()
    goal = State()
    goal_pace = State()
    diet_pattern = State()
    health_flags = State()
    allergies = State()
    meals_count = State()


class DietNotesEdit(StatesGroup):
    awaiting = State()
