"""SQLite storage for user profiles and the active plan.

We store just enough to remember the questionnaire between Telegram sessions,
so the user doesn't have to re-enter anthropometric data after `/start`.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from nutrition_bot.nutrition import Activity, Goal, Profile, Sex

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
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
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        # mkdir is fast/sync — fine to run inline before opening the async conn.
        Path(os.path.dirname(self._path) or ".").mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage is not opened")
        return self._db

    async def save_profile(
        self,
        user_id: int,
        profile: Profile,
        meals_count: int | None = None,
        diet_notes: str | None = None,
    ) -> None:
        await self._conn().execute(
            """
            INSERT INTO users (user_id, sex, age, weight_kg, height_cm, activity, goal,
                               meals_count, diet_notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                sex=excluded.sex,
                age=excluded.age,
                weight_kg=excluded.weight_kg,
                height_cm=excluded.height_cm,
                activity=excluded.activity,
                goal=excluded.goal,
                meals_count=COALESCE(excluded.meals_count, users.meals_count),
                diet_notes=COALESCE(excluded.diet_notes, users.diet_notes),
                updated_at=datetime('now')
            """,
            (
                user_id,
                profile.sex.value,
                profile.age,
                profile.weight_kg,
                profile.height_cm,
                profile.activity.value,
                profile.goal.value,
                meals_count,
                diet_notes,
            ),
        )
        await self._conn().commit()

    async def update_meals_count(self, user_id: int, meals_count: int) -> None:
        await self._conn().execute(
            "UPDATE users SET meals_count = ?, updated_at = datetime('now') WHERE user_id = ?",
            (meals_count, user_id),
        )
        await self._conn().commit()

    async def update_diet_notes(self, user_id: int, diet_notes: str) -> None:
        await self._conn().execute(
            "UPDATE users SET diet_notes = ?, updated_at = datetime('now') WHERE user_id = ?",
            (diet_notes, user_id),
        )
        await self._conn().commit()

    async def load_profile(self, user_id: int) -> tuple[Profile, int | None, str | None] | None:
        cur = await self._conn().execute(
            "SELECT sex, age, weight_kg, height_cm, activity, goal, meals_count, diet_notes "
            "FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            return None
        profile = Profile(
            sex=Sex(row["sex"]),
            age=int(row["age"]),
            weight_kg=float(row["weight_kg"]),
            height_cm=float(row["height_cm"]),
            activity=Activity(row["activity"]),
            goal=Goal(row["goal"]),
        )
        meals_count = int(row["meals_count"]) if row["meals_count"] is not None else None
        diet_notes = row["diet_notes"] if row["diet_notes"] is not None else None
        return profile, meals_count, diet_notes

    async def delete_profile(self, user_id: int) -> None:
        await self._conn().execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await self._conn().commit()
