"""Aggregate router for all bot handlers."""

from __future__ import annotations

from aiogram import Router

from nutrition_bot.handlers import meals, onboarding, plan


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(onboarding.router)
    root.include_router(plan.router)
    root.include_router(meals.router)
    return root
