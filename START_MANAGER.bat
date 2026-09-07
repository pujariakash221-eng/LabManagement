@echo off
setlocal

REM One-click launcher for the LabManagement manager/server on Windows.
REM The PowerShell script resolves the project root from its own location.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-manager.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo LabManagement Manager startup failed with exit code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
