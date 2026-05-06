"""SQLite storage round-trip tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from nutrition_bot.nutrition import Activity, Goal, Profile, Sex
from nutrition_bot.storage import Storage


@pytest.mark.asyncio
async def test_storage_roundtrip(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "bot.db"))
    await storage.open()
    try:
        profile = Profile(
            sex=Sex.female,
            age=28,
            weight_kg=62.5,
            height_cm=170,
            activity=Activity.light,
            goal=Goal.cut,
        )
        await storage.save_profile(123, profile, meals_count=4, diet_notes="без свинины")
        loaded = await storage.load_profile(123)
        assert loaded is not None
        loaded_profile, meals_count, notes = loaded
        assert loaded_profile == profile
        assert meals_count == 4
        assert notes == "без свинины"

        await storage.update_meals_count(123, 5)
        loaded2 = await storage.load_profile(123)
        assert loaded2 is not None
        assert loaded2[1] == 5

        await storage.delete_profile(123)
        assert await storage.load_profile(123) is None
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_storage_unknown_user_returns_none(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "bot.db"))
    await storage.open()
    try:
        assert await storage.load_profile(999) is None
    finally:
        await storage.close()
