"""FSM states for the onboarding questionnaire."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    sex = State()
    age = State()
    weight = State()
    height = State()
    activity = State()
    goal = State()
    meals_count = State()


class DietNotesEdit(StatesGroup):
    awaiting = State()
