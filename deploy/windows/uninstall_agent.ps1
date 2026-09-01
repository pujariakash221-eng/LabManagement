# ==============================================================================
# Computer Lab Management - Windows Lab Agent Uninstall Script
# ==============================================================================
# This script safely removes the LabManagement agent from this Windows computer.
# It will:
#   - Stop the running agent
#   - Remove the Windows scheduled task
#   - Optionally remove the configuration file
#   - NOT delete the LabManagement source code repository
#
# Usage (Run in PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\deploy\windows\uninstall_agent.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Red
Write-Host "  Computer Lab Management - Agent Uninstall" -ForegroundColor Red
Write-Host "==========================================================" -ForegroundColor Red
Write-Host ""

# Determine project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$EnvFile = Join-Path $ProjectRoot "agent.env"
$AgentIdentityFile = Join-Path $ProjectRoot "agent_id.json"

Write-Host "This will uninstall the LabManagement agent from this computer." -ForegroundColor Yellow
Write-Host ""
$Confirm = Read-Host "Do you want to continue? (yes/no)"

if ($Confirm -ne "yes") {
    Write-Host "Uninstall cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "[1/3] Stopping the agent..." -ForegroundColor Yellow

# Stop any running agent processes
$AgentProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "agent" }
if ($AgentProcesses) {
    foreach ($proc in $AgentProcesses) {
        try {
            Stop-Process -Id $proc.Id -Force
            Write-Host "      Stopped agent process (PID: $($proc.Id))" -ForegroundColor Green
        } catch {
            Write-Host "      Could not stop process PID $($proc.Id): $_" -ForegroundColor Yellow
        }
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host "      No agent processes found." -ForegroundColor Green
}

Write-Host "[2/3] Removing Windows scheduled task..." -ForegroundColor Yellow

$TaskName = "LabManagement Agent"
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
        Write-Host "      Scheduled task removed." -ForegroundColor Green
    } catch {
        Write-Host "      Warning: Could not remove scheduled task: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "      No scheduled task found." -ForegroundColor Green
}

Write-Host "[3/3] Cleaning up configuration..." -ForegroundColor Yellow

$CleanConfig = Read-Host "Do you want to remove the agent configuration files? (yes/no)"

if ($CleanConfig -eq "yes") {
    if (Test-Path $EnvFile) {
        Remove-Item -Path $EnvFile -Force -ErrorAction SilentlyContinue
        Write-Host "      Removed configuration file: $EnvFile" -ForegroundColor Green
    }
    
    if (Test-Path $AgentIdentityFile) {
        Remove-Item -Path $AgentIdentityFile -Force -ErrorAction SilentlyContinue
        Write-Host "      Removed agent identity file: $AgentIdentityFile" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "      Note: To re-register this agent, run:" -ForegroundColor Cyan
    Write-Host "        .\deploy\windows\setup_agent.ps1" -ForegroundColor Yellow
} else {
    Write-Host "      Configuration files preserved." -ForegroundColor Green
    Write-Host ""
    Write-Host "      Note: The LabManagement source code remains in:" -ForegroundColor Cyan
    Write-Host "        $ProjectRoot" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  Uninstall Complete" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
