# ==============================================================================
# Computer Lab Management - Windows Lab Agent Setup Script
# ==============================================================================
# This script sets up the Python virtual environment, installs dependencies,
# configures the server connection, and prepares the agent to run.
#
# Usage (Run in PowerShell as Administrator or standard user):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\deploy\windows\setup_agent.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Computer Lab Management - Windows Agent Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Determine project root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
Set-Location $ProjectRoot
Write-Host "[1/6] Working directory: $ProjectRoot" -ForegroundColor Green

# 2. Check for Python 3.12+
Write-Host "[2/6] Checking for Python installation..." -ForegroundColor Yellow
$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py -3"
} else {
    Write-Error "Python was not found on this system. Please install Python 3.12 or newer from https://www.python.org and check 'Add Python to PATH'."
}

$PyVersion = Invoke-Expression "$PythonCmd --version"
Write-Host "      Detected: $PyVersion" -ForegroundColor Green

# 3. Create or verify Virtual Environment
$VenvDir = Join-Path $ProjectRoot ".venv"
Write-Host "[3/6] Setting up virtual environment at $VenvDir..." -ForegroundColor Yellow
if (-not (Test-Path $VenvDir)) {
    Write-Host "      Creating new Python virtual environment..."
    Invoke-Expression "$PythonCmd -m venv .venv"
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment python binary not found at $VenvPython"
}
Write-Host "      Virtual environment ready." -ForegroundColor Green

# 4. Install Dependencies
Write-Host "[4/6] Installing required Python dependencies..." -ForegroundColor Yellow
$PipCmd = Join-Path $VenvDir "Scripts\pip.exe"
& $PipCmd install --upgrade pip --quiet
& $PipCmd install -r requirements.txt --quiet
Write-Host "      Dependencies installed successfully." -ForegroundColor Green

# 5. Configure Agent Settings (agent.env)
Write-Host "[5/6] Configuring agent connection settings..." -ForegroundColor Yellow
$EnvFile = Join-Path $ProjectRoot "agent.env"

if (-not (Test-Path $EnvFile)) {
    Write-Host ""
    Write-Host "Please enter the Central Lab Server configuration:" -ForegroundColor Cyan
    $ServerUrlInput = Read-Host "Server LAN URL (e.g. http://192.168.1.100:8000)"
    if ([string]::IsNullOrWhiteSpace($ServerUrlInput)) {
        $ServerUrlInput = "http://127.0.0.1:8000"
    }

    $AgentTokenInput = Read-Host "Agent Enrollment Token (from server configuration)"
    if ([string]::IsNullOrWhiteSpace($AgentTokenInput)) {
        $AgentTokenInput = "replace-with-same-agent-enrollment-secret-from-server"
    }

    $EnvContent = @"
# Computer Lab Management - Agent Configuration for Windows
LAB_SERVER_URL=$ServerUrlInput
LAB_AGENT_TOKEN=$AgentTokenInput
LAB_HEARTBEAT_INTERVAL=5.0
LAB_POWER_DRY_RUN=true
LAB_SCREEN_CAPTURE_INTERVAL=0.5
LAB_SCREEN_IMAGE_QUALITY=70
LAB_SCREEN_MAX_WIDTH=1920
LAB_SCREEN_MAX_HEIGHT=1080
LAB_SCREEN_MAX_FRAME_RATE=2.0
"@
    Set-Content -Path $EnvFile -Value $EnvContent -Encoding UTF8
    # Restrict file permissions to current user only
    icacls $EnvFile /inheritance:r /grant:r "${env:USERNAME}:F" | Out-Null
    Write-Host "      Created configuration at $EnvFile" -ForegroundColor Green
} else {
    Write-Host "      Existing configuration file found at $EnvFile" -ForegroundColor Green
}

# 6. Test Connectivity to Server
Write-Host "[6/6] Testing server connectivity..." -ForegroundColor Yellow
try {
    # Extract LAB_SERVER_URL from agent.env
    $ConfigLines = Get-Content $EnvFile
    $ServerUrl = "http://127.0.0.1:8000"
    foreach ($line in $ConfigLines) {
        if ($line -match "^LAB_SERVER_URL=(.+)$") {
            $ServerUrl = $matches[1].Trim()
        }
    }
    $HealthUrl = "$($ServerUrl.TrimEnd('/'))/api/health"
    Write-Host "      Pinging server at $HealthUrl..."
    $HealthResponse = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
    if ($HealthResponse.status -eq "running") {
        Write-Host "      Server is ONLINE and reachable!" -ForegroundColor Green
    }
} catch {
    Write-Host "      Note: Could not reach the server at $ServerUrl. Make sure the server is running on the LAN." -ForegroundColor Yellow
}

# 7. Configure Windows Auto-Start via Scheduled Task
Write-Host "[7/7] Configuring Windows auto-start..." -ForegroundColor Yellow

$TaskName = "LabManagement Agent"
$TaskPath = "\LabManagement\"
$PythonExePath = Join-Path $VenvDir "Scripts\python.exe"
$AgentScript = Join-Path $ProjectRoot "agent\__main__.py"

# Remove existing task if present (for idempotency)
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Write-Host "      Removing existing scheduled task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
}

# Create scheduled task
$TaskAction = New-ScheduledTaskAction -Execute $PythonExePath -Argument "-m agent.main"
$TaskTrigger = New-ScheduledTaskTrigger -AtStartup
$TaskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -StartWhenAvailable $true
$TaskPrincipal = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

try {
    Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Trigger $TaskTrigger -Settings $TaskSettings -Principal $TaskPrincipal -Force | Out-Null
    Write-Host "      Windows scheduled task created successfully." -ForegroundColor Green
    Write-Host "      The agent will automatically start when Windows boots." -ForegroundColor Green
} catch {
    Write-Host "      Warning: Could not create scheduled task. You may need to run this script as Administrator." -ForegroundColor Yellow
    Write-Host "      You can still start the agent manually with: .\deploy\windows\start_agent.bat" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Agent Configuration:" -ForegroundColor Cyan
Write-Host "    Project Directory: $ProjectRoot" -ForegroundColor White
Write-Host "    Config File:       $EnvFile" -ForegroundColor White
Write-Host "    Auto-Start:        Windows Scheduled Task" -ForegroundColor White
Write-Host ""
Write-Host "  To start the agent immediately:" -ForegroundColor Cyan
Write-Host "    .\deploy\windows\start_agent.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To view scheduled task:" -ForegroundColor Cyan
Write-Host "    Get-ScheduledTask -TaskName 'LabManagement Agent'" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To uninstall the agent:" -ForegroundColor Cyan
Write-Host "    .\deploy\windows\uninstall_agent.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green

