"""SQLite storage round-trip tests + migration coverage."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from nutrition_bot.nutrition import (
    Activity,
    DietPattern,
    Goal,
    GoalPace,
    HealthFlag,
    Profile,
    Sex,
)
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
            waist_cm=78.0,
            diet_pattern=DietPattern.mediterranean,
            goal_pace=GoalPace.slow,
            health_flags=frozenset({HealthFlag.hypertension, HealthFlag.high_cholesterol}),
            allergies="орехи, креветки",
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


@pytest.mark.asyncio
async def test_storage_legacy_row_loads_with_defaults(tmp_path: Path) -> None:
    """An older DB written before the personalisation columns existed must
    still load: missing columns get neutral defaults so existing users are
    not bricked by the migration."""
    db_path = tmp_path / "legacy.db"
    # Hand-craft an old-schema database with only the original columns.
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(
            """
            CREATE TABLE users (
                user_id      INTEGER PRIMARY KEY,
                sex          TEXT    NOT NULL,
                age          INTEGER NOT NULL,
                weight_kg    REAL    NOT NULL,
                height_cm    REAL    NOT NULL,
                activity     TEXT    NOT NULL,
                goal         TEXT    NOT NULL,
                meals_count  INTEGER,
                diet_notes   TEXT,
                updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO users (user_id, sex, age, weight_kg, height_cm, activity, goal, meals_count, diet_notes)
            VALUES (42, 'male', 35, 78, 178, 'moderate', 'maintain', 4, NULL);
            """
        )
        await db.commit()

    storage = Storage(str(db_path))
    await storage.open()
    try:
        loaded = await storage.load_profile(42)
        assert loaded is not None
        profile, meals_count, notes = loaded
        assert profile.sex is Sex.male
        assert profile.age == 35
        # New columns came from migration defaults.
        assert profile.diet_pattern is DietPattern.balanced
        assert profile.goal_pace is GoalPace.standard
        assert profile.waist_cm is None
        assert profile.health_flags == frozenset()
        assert profile.allergies == ""
        assert meals_count == 4
        assert notes is None
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_storage_migration_idempotent(tmp_path: Path) -> None:
    """Opening an already-migrated DB twice must not error or duplicate columns."""
    db_path = tmp_path / "twice.db"
    s1 = Storage(str(db_path))
    await s1.open()
    await s1.close()
    s2 = Storage(str(db_path))
    await s2.open()
    try:
        # Sanity write/read after second open.
        profile = Profile(
            sex=Sex.male,
            age=40,
            weight_kg=82,
            height_cm=180,
            activity=Activity.moderate,
            goal=Goal.maintain,
            health_flags=frozenset({HealthFlag.diabetes_t2}),
            allergies="",
        )
        await s2.save_profile(7, profile, meals_count=3)
        loaded = await s2.load_profile(7)
        assert loaded is not None
        assert HealthFlag.diabetes_t2 in loaded[0].health_flags
    finally:
        await s2.close()
