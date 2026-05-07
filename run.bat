@echo off
rem One-click launcher for nutrition-bot (Windows).
rem
rem Picks Python 3.11+, builds .venv, installs deps, bootstraps .env,
rem then runs `python -m nutrition_bot`. The local LLM server (Qwen2.5-14B)
rem must already be running -- see README.

setlocal enableextensions
cd /d "%~dp0"

rem --- Find Python -----------------------------------------------------------
set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py -3"
)
if not defined PY_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY_CMD=python"
    )
)
if not defined PY_CMD (
    echo ERROR: Python 3.11+ not found. Install Python from https://www.python.org/ and re-run.
    pause
    exit /b 1
)

rem --- Virtualenv ------------------------------------------------------------
if not exist ".venv" (
    echo Creating virtualenv in .venv ...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo ERROR: failed to create .venv
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

if not exist ".venv\.installed" (
    echo Installing dependencies ...
    python -m pip install --upgrade pip --quiet
    if errorlevel 1 (
        echo ERROR: pip upgrade failed
        pause
        exit /b 1
    )
    python -m pip install -e . --quiet
    if errorlevel 1 (
        echo ERROR: dependency install failed
        pause
        exit /b 1
    )
    type nul > ".venv\.installed"
)

rem --- .env ------------------------------------------------------------------
if not exist ".env" (
    if not exist ".env.example" (
        echo ERROR: neither .env nor .env.example found
        pause
        exit /b 1
    )
    copy /Y ".env.example" ".env" >nul
    echo.
    echo Created .env from .env.example.
    echo Open .env and fill in TELEGRAM_BOT_TOKEN ^(get one from @BotFather^),
    echo also check OPENAI_BASE_URL and OPENAI_MODEL for your local LLM server.
    echo Then re-run this script.
    pause
    exit /b 1
)

findstr /R /C:"^TELEGRAM_BOT_TOKEN=..*" ".env" >nul
if errorlevel 1 (
    echo ERROR: TELEGRAM_BOT_TOKEN is empty in .env. Get a token from @BotFather and set it.
    pause
    exit /b 1
)

rem --- Run -------------------------------------------------------------------
echo Starting nutrition-bot ...
python -m nutrition_bot
set "RC=%ERRORLEVEL%"
echo.
echo Bot exited with code %RC%.
pause
exit /b %RC%
