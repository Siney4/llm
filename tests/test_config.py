"""Basic config parsing tests."""

from __future__ import annotations

import pytest

from bot.config import Settings


def test_settings_parses_csv_lists(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a real .env in repo root
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anth")
    monkeypatch.setenv("OPENAI_MODELS", "gpt-a, gpt-b ,gpt-c")
    monkeypatch.setenv("ANTHROPIC_MODELS", "claude-a,claude-b")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222")
    monkeypatch.setenv("ADMIN_USER_IDS", "")

    s = Settings()  # type: ignore[call-arg]

    assert s.telegram_bot_token == "tg-xxx"
    assert s.openai_models == ["gpt-a", "gpt-b", "gpt-c"]
    assert s.anthropic_models == ["claude-a", "claude-b"]
    assert s.allowed_user_ids == [111, 222]
    assert s.admin_user_ids == []
    assert s.has_openai()
    assert s.has_anthropic()


def test_settings_rejects_bad_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-xxx")
    monkeypatch.setenv("DEFAULT_PROVIDER", "google")
    with pytest.raises(ValueError):
        Settings()  # type: ignore[call-arg]
