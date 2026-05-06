# nutrition-bot

Telegram-бот для составления персонального плана питания. Считает BMR/TDEE/КБЖУ, раскладывает дневной калораж по 3–5 приёмам пищи с буфером на «вкусняшки» (правило 80/20), и генерирует конкретные блюда через локальный **Qwen2.5-14B-Instruct (Q4_K_M)**.

Вся арифметика — чистый Python. LLM используется только для творческой части — генерации идеи блюда под целевой калораж/КБЖУ.

## Что умеет

- Анкета: пол → возраст → вес → рост → уровень активности → цель → число приёмов пищи
- Расчёт BMR (Mifflin–St Jeor) и TDEE по PAL-таблице (Sedentary 1.2 … Extra 1.9)
- Цель: похудение (−500), поддержка (0), набор (+300)
- КБЖУ: 2.0 г/кг белок, 1.0 г/кг жир, остальное — углеводы
- Раскладка по приёмам пищи (3/4/5) + буфер 15% на вкусняшки/срывы
- Команды: `/start`, `/plan`, `/meal`, `/notes`, `/reset`
- Кнопка «Другой вариант» — пересоздать блюдо
- Учёт ограничений (вегетарианец, без свинины и т.д.) через `/notes`

## Архитектура

```
src/nutrition_bot/
  nutrition.py       # BMR / TDEE / макросы / распределение по приёмам (чистый Python)
  llm.py             # OpenAI-совместимый клиент + промпты для блюд
  storage.py         # SQLite (aiosqlite) для профиля
  config.py          # pydantic-settings, .env
  fsm.py             # состояния FSM анкеты
  keyboards.py       # inline-клавиатуры
  formatting.py      # рендер плана в текст
  handlers/          # /start, /plan, /meal, /notes, /reset, callback'и
  bot.py             # сборка и запуск aiogram dispatcher
```

LLM-клиент — обычный OpenAI SDK против OpenAI-совместимого `/v1/chat/completions`. Это работает с любым из:

| Сервер           | Команда                                                                | Endpoint                    |
| ---------------- | ---------------------------------------------------------------------- | --------------------------- |
| llama.cpp        | `llama-server -m Qwen2.5-14B-Instruct-Q4_K_M.gguf -c 8192`             | `http://localhost:8080/v1`  |
| Ollama           | `ollama pull qwen2.5:14b-instruct-q4_K_M && ollama serve`              | `http://localhost:11434/v1` |
| vLLM             | `vllm serve Qwen/Qwen2.5-14B-Instruct --quantization awq` (или GPTQ)   | `http://localhost:8000/v1`  |
| LM Studio        | Запусти локальный сервер из UI                                         | `http://localhost:1234/v1`  |

## Быстрый старт

```bash
# 1. Установить
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Поднять LLM (любой из вариантов выше). Пример для llama.cpp:
#    скачай Qwen2.5-14B-Instruct-Q4_K_M.gguf и запусти:
#    llama-server -m Qwen2.5-14B-Instruct-Q4_K_M.gguf -c 8192

# 3. Создать .env
cp .env.example .env
# заполни TELEGRAM_BOT_TOKEN (из @BotFather) и при необходимости OPENAI_BASE_URL / OPENAI_MODEL

# 4. Запустить бота
python -m nutrition_bot
# или: nutrition-bot
```

## Конфигурация (`.env`)

| Переменная             | Назначение                                                  | По умолчанию                       |
| ---------------------- | ----------------------------------------------------------- | ---------------------------------- |
| `TELEGRAM_BOT_TOKEN`   | Токен от @BotFather                                         | —                                  |
| `OPENAI_BASE_URL`      | URL OpenAI-совместимого endpoint                            | `http://localhost:8080/v1`         |
| `OPENAI_API_KEY`       | Любая строка для llama.cpp / Ollama (заглушка)              | `sk-no-key-required`               |
| `OPENAI_MODEL`         | Имя модели в endpoint                                       | `Qwen2.5-14B-Instruct-Q4_K_M`      |
| `LLM_TEMPERATURE`      | Температура генерации блюд                                  | `0.7`                              |
| `LLM_MAX_TOKENS`       | Лимит выходных токенов                                      | `900`                              |
| `LLM_TIMEOUT_S`        | Таймаут запроса к LLM                                       | `120`                              |
| `BUFFER_FRACTION`      | Доля TDEE на «вкусняшки» (правило 80/20)                    | `0.15`                             |
| `DB_PATH`              | Путь к SQLite                                               | `data/nutrition.db`                |
| `ALLOWED_USER_IDS`     | Через запятую — белый список TG user-ID, пусто = открыт всем| —                                  |
| `LOG_LEVEL`            | Уровень логирования                                         | `INFO`                             |

## Разработка

```bash
ruff check src tests
ruff format src tests
mypy
pytest -q
```

## Запуск в Docker

```bash
docker build -t nutrition-bot .
docker run --rm -d --name nutrition-bot \
  --network host \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  nutrition-bot
```

`--network host` нужен, чтобы контейнер достучался до локально запущенного `llama-server` / `ollama` на хосте. На macOS / Windows используй `host.docker.internal` в `OPENAI_BASE_URL` вместо `localhost`.

## Лицензия

MIT
