"""DB repo smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.db import open_repo


@pytest.mark.asyncio
async def test_repo_flow(tmp_path: Path) -> None:
    db = tmp_path / "bot.db"
    async with open_repo(str(db)) as repo:
        assert await repo.get_user(42) is None

        await repo.upsert_user(42, "openai", "gpt-a")
        user = await repo.get_user(42)
        assert user is not None
        assert user.provider == "openai"
        assert user.model == "gpt-a"

        await repo.append_message(42, "user", "hi")
        await repo.append_message(42, "assistant", "hello")
        await repo.append_message(42, "user", "how are you?")

        history = await repo.get_history(42, limit=10)
        assert [m.role for m in history] == ["user", "assistant", "user"]
        assert history[0].content == "hi"
        assert history[-1].content == "how are you?"

        users, msgs = await repo.stats()
        assert users == 1
        assert msgs == 3

        await repo.reset(42)
        assert await repo.get_history(42, limit=10) == []
