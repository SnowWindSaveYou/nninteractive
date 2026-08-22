@echo off
REM Stop any process listening on port 18080, then relaunch the backend in LOCAL GPU mode.
REM Usage: double-click or run from a cmd window.

setlocal

set CONDA_ENV_DIR=D:\Programs\miniconda3\envs\nninteractive
set PYTHON=%CONDA_ENV_DIR%\python.exe
set SERVICE_DIR=%~dp0
set PORT=18080

REM --- Stop any existing server on the port ---
echo Stopping any process on port %PORT% ...
for /f "tokens=5" %%a in ('netstat -ano -p TCP ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo   killing PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM Give the socket a moment to free up.
timeout /t 1 /nobreak >nul

REM --- (Re)start ---
REM Business config (engine, model_dir, allowed_data_roots, etc.) is read from
REM the .env file in SERVICE_DIR. Do NOT set NNINTERACTIVE_BACKEND_* here —
REM real env vars override .env, so setting them in this script would make
REM .env edits take no effect. Edit .env (from .env.example) to configure.
REM Only PYTHONPATH (runtime wiring) is set here.
set PYTHONPATH=%SERVICE_DIR%

cd /d "%SERVICE_DIR%"

echo Restarting nnInteractive backend (local GPU) on http://0.0.0.0:%PORT%
echo (config loaded from %SERVICE_DIR%.env — edit it to change engine/roots/model)
"%PYTHON%" -m uvicorn nninteractive_service.main:app --host 0.0.0.0 --port %PORT%

endlocal
