[CmdletBinding()]
param()

# Creates one explicit inbound rule for the default LabManagement manager port.
# The rule is limited to Windows' Private profile; it does not disable or alter
# any other Windows Firewall settings.

$ErrorActionPreference = "Stop"
$ruleName = "LabManagement Manager TCP 8000"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    throw "Administrator rights are required to create a Windows Firewall rule. Re-open PowerShell as Administrator and run this script again."
}

if (-not (Get-Command New-NetFirewallRule -ErrorAction SilentlyContinue)) {
    throw "Windows Firewall cmdlets are unavailable on this system. Create an inbound TCP rule for port 8000 on the Private profile through Windows Defender Firewall."
}

$existingRule = @(Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)
if ($existingRule.Count -gt 0) {
    Write-Host "The Windows Firewall rule '$ruleName' already exists. No changes were made." -ForegroundColor Green
    exit 0
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Description "Allows LabManagement manager dashboard and agent traffic on TCP port 8000 for Private networks." `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8000 `
    -Profile Private `
    -Enabled True | Out-Null

Write-Host "Created Windows Firewall rule '$ruleName' for inbound TCP port 8000 on Private networks." -ForegroundColor Green
