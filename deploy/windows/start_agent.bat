@echo off
REM ==============================================================================
REM Computer Lab Management - Windows Agent Startup Script
REM ==============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0\..\.."

echo ==========================================================
echo  Starting Computer Lab Management Agent (Windows)
echo ==========================================================

REM Check virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run:
    echo powershell -ExecutionPolicy Bypass -File deploy\windows\setup_agent.ps1
    pause
    exit /b 1
)

REM Load environment variables from agent.env or .env if present
if exist "agent.env" (
    echo Loading configuration from agent.env...
    for /f "usebackq tokens=1,* delims==" %%A in ("agent.env") do (
        set "line=%%A"
        if not "!line:~0,1!"=="#" (
            set "%%A=%%B"
        )
    )
) else if exist ".env" (
    echo Loading configuration from .env...
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "line=%%A"
        if not "!line:~0,1!"=="#" (
            set "%%A=%%B"
        )
    )
)

echo Target Server: %LAB_SERVER_URL%
echo Power Dry-Run: %LAB_POWER_DRY_RUN%

REM Launch agent via virtual environment Python
.venv\Scripts\python.exe -m agent.main

if errorlevel 1 (
    echo [ERROR] Agent stopped with error code %errorlevel%.
    pause
)

