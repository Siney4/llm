@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

rem One-click launcher for nutrition-bot (Windows).
rem
rem Same flow as run.sh: find Python 3.11+, create .venv, install deps,
rem bootstrap .env, run the bot. The LLM server (Qwen2.5-14B) must already
rem be running locally — see README.

cd /d "%~dp0"

rem --- Find Python -----------------------------------------------------------
set "PY=%PYTHON%"
if "%PY%"=="" (
  for %%C in (py python python3) do (
    where %%C >nul 2>&1
    if not errorlevel 1 (
      set "PY=%%C"
      goto found_py
    )
  )
)
:found_py
if "%PY%"=="" (
  echo Python 3.11+ не найден. Установи Python с https://www.python.org/ и повтори запуск.
  pause
  exit /b 1
)

rem 'py' supports the -3.11 selector; fall back to plain command otherwise.
if /I "%PY%"=="py" (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=%PY%"
)

%PY_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo Нужен Python 3.11 или новее. Поставь свежий Python и повтори.
  pause
  exit /b 1
)

rem --- Virtualenv ------------------------------------------------------------
if not exist ".venv" (
  echo Создаю виртуальное окружение в .venv...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo Не удалось создать .venv.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"

if not exist ".venv\.installed" (
  echo Устанавливаю зависимости...
  python -m pip install --upgrade pip --quiet
  python -m pip install -e . --quiet
  if errorlevel 1 (
    echo Установка зависимостей упала.
    pause
    exit /b 1
  )
  type nul > ".venv\.installed"
)

rem --- .env ------------------------------------------------------------------
if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo.
    echo Создал .env из .env.example.
    echo Открой его и впиши TELEGRAM_BOT_TOKEN ^(получить у @BotFather^),
    echo проверь OPENAI_BASE_URL и OPENAI_MODEL.
    echo После этого запусти скрипт снова.
    pause
    exit /b 1
  ) else (
    echo Нет ни .env, ни .env.example.
    pause
    exit /b 1
  )
)

findstr /R /C:"^TELEGRAM_BOT_TOKEN=..*" ".env" >nul
if errorlevel 1 (
  echo В .env пустой TELEGRAM_BOT_TOKEN. Получи токен у @BotFather и впиши.
  pause
  exit /b 1
)

rem --- Run -------------------------------------------------------------------
echo Запускаю nutrition-bot...
python -m nutrition_bot
set "RC=%errorlevel%"
echo.
echo Бот завершил работу с кодом %RC%.
pause
exit /b %RC%
