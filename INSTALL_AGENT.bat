@echo off
setlocal

REM One-click launcher for an existing LabManagement checkout.
REM The elevated child prompts for the server URL and enrollment secret.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0install-agent.ps1""'; exit $process.ExitCode"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo LabManagement agent installation failed with exit code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
