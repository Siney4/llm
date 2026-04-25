"""Registry building tests."""

from __future__ import annotations

import pytest

from bot.config import Settings
from bot.providers import build_registry


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    openai: bool = True,
    anthropic: bool = True,
) -> Settings:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-xxx")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai" if openai else "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anth" if anthropic else "")
    monkeypatch.setenv("OPENAI_MODELS", "gpt-a,gpt-b")
    monkeypatch.setenv("ANTHROPIC_MODELS", "claude-a,claude-b")
    return Settings()  # type: ignore[call-arg]


def test_registry_both(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path)
    reg = build_registry(s)
    assert set(reg.available()) == {"openai", "anthropic"}
    provider, model = reg.pick_default()
    assert provider == "openai"
    assert model == "gpt-a"
    assert reg.is_valid_pair("anthropic", "claude-b")
    assert not reg.is_valid_pair("openai", "nope")


def test_registry_only_anthropic(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path, openai=False)
    reg = build_registry(s)
    assert reg.available() == ["anthropic"]
    provider, model = reg.pick_default()
    assert provider == "anthropic"
    assert model == "claude-a"


def test_registry_no_providers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    s = _settings(monkeypatch, tmp_path, openai=False, anthropic=False)
    with pytest.raises(RuntimeError):
        build_registry(s)
