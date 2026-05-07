#!/usr/bin/env bash
# One-click launcher for nutrition-bot (Linux / macOS).
#
# What it does:
#   1. Picks the first available Python ≥ 3.11 (or the one in $PYTHON).
#   2. Creates / reuses a `.venv/` virtualenv next to this script.
#   3. Installs the project (pyproject.toml) on first run, or after edits.
#   4. Bootstraps `.env` from `.env.example` and asks you to fill in the token.
#   5. Runs `python -m nutrition_bot`.
#
# The local LLM server (e.g. `llama-server` for Qwen2.5-14B-Instruct Q4_K_M)
# must already be running — see README for the command. The bot just talks to
# whatever you put in OPENAI_BASE_URL.

set -euo pipefail

cd "$(dirname "$0")"

# --- Locate Python 3.11+ -------------------------------------------------------
PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  for cand in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
      PY="$cand"
      break
    fi
  done
fi
if [[ -z "$PY" ]]; then
  echo "❌ Python 3.11+ не найден. Установи Python и повтори запуск." >&2
  exit 1
fi

VER=$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
MAJOR=${VER%%.*}
MINOR=${VER##*.}
if (( MAJOR < 3 || (MAJOR == 3 && MINOR < 11) )); then
  echo "❌ Нужен Python 3.11+, у тебя $VER ($PY). Установи свежий Python и повтори." >&2
  exit 1
fi

# --- Virtualenv ----------------------------------------------------------------
if [[ ! -d .venv ]]; then
  echo "📦 Создаю виртуальное окружение в .venv (Python $VER)..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Reinstall when pyproject.toml changes (or first run).
STAMP=".venv/.installed"
if [[ ! -f "$STAMP" || pyproject.toml -nt "$STAMP" ]]; then
  echo "📦 Устанавливаю зависимости..."
  python -m pip install --upgrade pip --quiet
  python -m pip install -e . --quiet
  : > "$STAMP"
fi

# --- .env ----------------------------------------------------------------------
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo
    echo "⚠️  Создал .env из .env.example."
    echo "   Открой его и впиши TELEGRAM_BOT_TOKEN (получить у @BotFather),"
    echo "   проверь OPENAI_BASE_URL и OPENAI_MODEL под свой LLM-сервер."
    echo "   После этого запусти скрипт снова."
    exit 1
  else
    echo "❌ Нет ни .env, ни .env.example — нечего читать настройки." >&2
    exit 1
  fi
fi

# Empty token = bot won't start anyway, fail fast with a clear message.
if ! grep -Eq '^TELEGRAM_BOT_TOKEN=[^[:space:]]+' .env; then
  echo "❌ В .env пустой TELEGRAM_BOT_TOKEN. Получи токен у @BotFather и впиши." >&2
  exit 1
fi

# --- Run -----------------------------------------------------------------------
echo "🚀 Запускаю nutrition-bot..."
exec python -m nutrition_bot
