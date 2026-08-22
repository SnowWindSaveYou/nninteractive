@echo off
REM Launch the nnInteractive backend in LOCAL GPU mode.
REM Usage: double-click or run from a cmd window.
REM Requires: conda env "nninteractive" at D:\Programs\miniconda3

setlocal

set CONDA_ENV_DIR=D:\Programs\miniconda3\envs\nninteractive
set PYTHON=%CONDA_ENV_DIR%\python.exe
set SERVICE_DIR=%~dp0

REM Business config (engine, model_dir, allowed_data_roots, etc.) is read from
REM the .env file in SERVICE_DIR. Do NOT set NNINTERACTIVE_BACKEND_* here —
REM real env vars override .env, so setting them in this script would make
REM .env edits take no effect. Edit .env (from .env.example) to configure.
set PYTHONPATH=%SERVICE_DIR%

cd /d "%SERVICE_DIR%"

echo Starting nnInteractive backend (local GPU) on http://0.0.0.0:18080
echo (config loaded from %SERVICE_DIR%.env — edit it to change engine/roots/model)
"%PYTHON%" -m uvicorn nninteractive_service.main:app --host 0.0.0.0 --port 18080

endlocal
