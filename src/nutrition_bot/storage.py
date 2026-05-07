"""SQLite storage for user profiles and the active plan.

We store just enough to remember the questionnaire between Telegram sessions,
so the user doesn't have to re-enter anthropometric data after `/start`.

Schema migrations are forward-only and idempotent: every new column is added
inside a `_migrate()` step that checks `PRAGMA table_info(users)` first, so
upgrades from older schemas keep existing data intact.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from nutrition_bot.nutrition import (
    Activity,
    DietPattern,
    Goal,
    GoalPace,
    HealthFlag,
    Profile,
    Sex,
)

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

# (column_name, ALTER TABLE clause). Applied in order; each is gated on a
# fresh PRAGMA snapshot so adding a column twice is a no-op.
_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("waist_cm", "ALTER TABLE users ADD COLUMN waist_cm REAL"),
    (
        "diet_pattern",
        "ALTER TABLE users ADD COLUMN diet_pattern TEXT NOT NULL DEFAULT 'balanced'",
    ),
    (
        "goal_pace",
        "ALTER TABLE users ADD COLUMN goal_pace TEXT NOT NULL DEFAULT 'standard'",
    ),
    (
        "health_flags",
        "ALTER TABLE users ADD COLUMN health_flags TEXT NOT NULL DEFAULT ''",
    ),
    ("allergies", "ALTER TABLE users ADD COLUMN allergies TEXT NOT NULL DEFAULT ''"),
)


def _encode_health_flags(flags: frozenset[HealthFlag]) -> str:
    """Comma-separated stable encoding (sorted for reproducibility)."""
    return ",".join(sorted(f.value for f in flags))


def _decode_health_flags(raw: str | None) -> frozenset[HealthFlag]:
    if not raw:
        return frozenset()
    out: set[HealthFlag] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        # Defensive: skip unknown values rather than crash an existing user.
        try:
            out.add(HealthFlag(token))
        except ValueError:
            continue
    return frozenset(out)


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
        await self._migrate()
        await self._db.commit()

    async def _migrate(self) -> None:
        assert self._db is not None
        cur = await self._db.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        for col, ddl in _MIGRATIONS:
            if col not in cols:
                await self._db.execute(ddl)

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
            INSERT INTO users (
                user_id, sex, age, weight_kg, height_cm, activity, goal,
                meals_count, diet_notes,
                waist_cm, diet_pattern, goal_pace, health_flags, allergies,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                sex=excluded.sex,
                age=excluded.age,
                weight_kg=excluded.weight_kg,
                height_cm=excluded.height_cm,
                activity=excluded.activity,
                goal=excluded.goal,
                meals_count=COALESCE(excluded.meals_count, users.meals_count),
                diet_notes=COALESCE(excluded.diet_notes, users.diet_notes),
                waist_cm=excluded.waist_cm,
                diet_pattern=excluded.diet_pattern,
                goal_pace=excluded.goal_pace,
                health_flags=excluded.health_flags,
                allergies=excluded.allergies,
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
                profile.waist_cm,
                profile.diet_pattern.value,
                profile.goal_pace.value,
                _encode_health_flags(profile.health_flags),
                profile.allergies,
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
            "SELECT sex, age, weight_kg, height_cm, activity, goal, "
            "meals_count, diet_notes, waist_cm, diet_pattern, goal_pace, "
            "health_flags, allergies "
            "FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            return None
        # Defensive defaults — older rows or unknown values fall back to the
        # neutral defaults so a corrupted column never blocks a user.
        try:
            diet_pattern = DietPattern(row["diet_pattern"] or "balanced")
        except ValueError:
            diet_pattern = DietPattern.balanced
        try:
            goal_pace = GoalPace(row["goal_pace"] or "standard")
        except ValueError:
            goal_pace = GoalPace.standard
        profile = Profile(
            sex=Sex(row["sex"]),
            age=int(row["age"]),
            weight_kg=float(row["weight_kg"]),
            height_cm=float(row["height_cm"]),
            activity=Activity(row["activity"]),
            goal=Goal(row["goal"]),
            waist_cm=float(row["waist_cm"]) if row["waist_cm"] is not None else None,
            diet_pattern=diet_pattern,
            goal_pace=goal_pace,
            health_flags=_decode_health_flags(row["health_flags"]),
            allergies=row["allergies"] or "",
        )
        meals_count = int(row["meals_count"]) if row["meals_count"] is not None else None
        diet_notes = row["diet_notes"] if row["diet_notes"] is not None else None
        return profile, meals_count, diet_notes

    async def delete_profile(self, user_id: int) -> None:
        await self._conn().execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await self._conn().commit()
