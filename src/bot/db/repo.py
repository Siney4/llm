"""SQLite-backed repository for users and conversation history."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiosqlite

from bot.providers.base import ChatMessage

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    provider       TEXT    NOT NULL,
    model          TEXT    NOT NULL,
    created_at     INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at     INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    role       TEXT    NOT NULL CHECK (role IN ('user','assistant')),
    content    TEXT    NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_user_created
    ON messages(user_id, created_at DESC);
"""


@dataclass(slots=True)
class UserRow:
    user_id: int
    provider: str
    model: str


class Repo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def init(self) -> None:
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def upsert_user(self, user_id: int, provider: str, model: str) -> None:
        await self._db.execute(
            """
            INSERT INTO users (user_id, provider, model)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                provider   = excluded.provider,
                model      = excluded.model,
                updated_at = strftime('%s','now')
            """,
            (user_id, provider, model),
        )
        await self._db.commit()

    async def get_user(self, user_id: int) -> UserRow | None:
        async with self._db.execute(
            "SELECT user_id, provider, model FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return UserRow(user_id=row[0], provider=row[1], model=row[2])

    async def set_selection(self, user_id: int, provider: str, model: str) -> None:
        await self.upsert_user(user_id, provider, model)

    async def append_message(self, user_id: int, role: str, content: str) -> None:
        assert role in {"user", "assistant"}
        await self._db.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        await self._db.commit()

    async def get_history(self, user_id: int, limit: int) -> list[ChatMessage]:
        async with self._db.execute(
            """
            SELECT role, content FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        # DB returns newest-first; reverse so the chat flows oldest-first.
        ordered = list(rows)
        ordered.reverse()
        return [ChatMessage(role=r[0], content=r[1]) for r in ordered]

    async def reset(self, user_id: int) -> None:
        await self._db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await self._db.commit()

    async def stats(self) -> tuple[int, int]:
        async with self._db.execute("SELECT COUNT(*) FROM users") as cur:
            users_row = await cur.fetchone()
        async with self._db.execute("SELECT COUNT(*) FROM messages") as cur:
            msgs_row = await cur.fetchone()
        return (users_row[0] if users_row else 0, msgs_row[0] if msgs_row else 0)


@asynccontextmanager
async def open_repo(db_path: str) -> AsyncIterator[Repo]:
    dirpath = os.path.dirname(os.path.abspath(db_path))  # noqa: ASYNC240 - sync FS op at startup is fine
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)  # noqa: ASYNC240
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        repo = Repo(db)
        await repo.init()
        yield repo
