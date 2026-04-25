# tg-llm-aggregator

Telegram bot that aggregates **OpenAI (ChatGPT)** and **Anthropic (Claude)** into a single chat UI. Pick a provider and model, chat normally — the bot streams replies back, keeps conversation history per user, and switches models on demand.

Built with [aiogram 3](https://aiogram.dev), the official `openai` and `anthropic` async SDKs, and SQLite (via `aiosqlite`) for history.

## Features

- Inline picker for provider → model (`/model`)
- Streaming responses — the bot edits a single message as tokens arrive
- Per-user conversation history in SQLite; `/reset` to clear
- System prompt, history window and model lists are all env-configurable
- No hardcoded model IDs — point `OPENAI_MODELS` / `ANTHROPIC_MODELS` at whatever models your account has access to (GPT-5, Claude Opus 4.5, or whatever ships next)
- Optional allow-list (`ALLOWED_USER_IDS`) and admin IDs (`ADMIN_USER_IDS` → `/stats`)
- Clean `LLMProvider` abstraction — add a third provider in ~50 LOC
- Dockerfile + `docker-compose.yml` included

## Quick start

### 1. Create a Telegram bot

Open [@BotFather](https://t.me/BotFather), send `/newbot`, follow the steps. Copy the bot token.

### 2. Get API keys

- OpenAI: <https://platform.openai.com/api-keys>
- Anthropic: <https://console.anthropic.com/settings/keys>

You only need to configure the provider(s) you plan to use; the other one can stay empty.

### 3. Configure `.env`

```bash
cp .env.example .env
$EDITOR .env
```

Minimal `.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_MODELS=gpt-4o,gpt-4o-mini
ANTHROPIC_MODELS=claude-3-5-sonnet-latest,claude-3-5-haiku-latest
DEFAULT_PROVIDER=openai
```

> Update `OPENAI_MODELS` / `ANTHROPIC_MODELS` to whatever your accounts have access to. New models released? Just change the string, no code changes required.

### 4a. Run locally (Python)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m bot
```

### 4b. Run with Docker

```bash
docker compose up --build -d
docker compose logs -f bot
```

Data (SQLite DB) is persisted to `./data/`.

## Usage

Send `/start` to the bot. Then:

| Command   | Description                                  |
|-----------|----------------------------------------------|
| `/start`  | Intro + current model                        |
| `/help`   | Show help                                    |
| `/model`  | Inline picker: provider → model              |
| `/models` | List all available models                    |
| `/reset`  | Clear your conversation history              |
| `/stats`  | Users and message count (admins only)        |

Any plain message is forwarded to the selected model. Long responses are streamed into the same Telegram message (up to ~4000 chars) and split across follow-up messages if longer.

## Project layout

```
src/bot/
  __main__.py           # python -m bot
  main.py               # wires Dispatcher, DB, providers
  config.py             # pydantic-settings from .env
  keyboards.py          # inline keyboards
  handlers/
    commands.py         # /start /help /model /reset /stats
    messages.py         # streaming chat pipeline
  providers/
    base.py             # LLMProvider ABC + ChatMessage
    openai_provider.py  # AsyncOpenAI
    anthropic_provider.py  # AsyncAnthropic
    registry.py         # build registry from settings
  db/
    repo.py             # users + messages in SQLite
tests/
  test_config.py
  test_registry.py
  test_repo.py
```

## Adding a new provider

1. Create `src/bot/providers/<name>_provider.py` that subclasses `LLMProvider` and implements `stream_chat`.
2. Register it in `src/bot/providers/registry.py::build_registry`.
3. Add a row for it in `.env.example`.
4. Add it to `bot/keyboards.py::_pretty_provider` for a nicer label.

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
mypy
pytest -q
```

## Security notes

- Never commit `.env` or any `*.db` file.
- Use `ALLOWED_USER_IDS` to restrict the bot to a private group while you're testing.
- Rotate API keys if you ever suspect they leaked.

## Roadmap

- [ ] Payments (Telegram Stars / ЮKassa / Stripe) + daily free-message limit
- [ ] Image input (gpt-4o vision, Claude vision)
- [ ] Voice input (Whisper → LLM)
- [ ] Web search / tool-calling
- [ ] Per-user temperature / custom system prompt
- [ ] Admin broadcast command

## License

MIT.
