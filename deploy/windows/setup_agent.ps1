[CmdletBinding()]
param(
    [string]$ServerUrl,
    [SecureString]$EnrollmentSecret,
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-ProjectRoot {
    param([string]$ExplicitProjectRoot)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitProjectRoot)) {
        $candidate = [Environment]::ExpandEnvironmentVariables($ExplicitProjectRoot.Trim())
        try { $candidate = [IO.Path]::GetFullPath($candidate) } catch { throw "ProjectRoot is invalid: '$ExplicitProjectRoot'. Details: $($_.Exception.Message)" }
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { throw "ProjectRoot does not exist or is not a directory: '$candidate'." }
        if (-not (Test-Path -LiteralPath (Join-Path $candidate 'deploy\windows\setup_agent.ps1') -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $candidate 'requirements.txt') -PathType Leaf)) {
            throw "ProjectRoot is not a valid LabManagement installation: '$candidate'."
        }
        return (Resolve-Path -LiteralPath $candidate).Path
    }
    $scriptPath = $null
    if (-not [string]::IsNullOrWhiteSpace($PSCommandPath)) { $scriptPath = $PSCommandPath }
    elseif ($MyInvocation -and -not [string]::IsNullOrWhiteSpace($MyInvocation.MyCommand.Path)) { $scriptPath = $MyInvocation.MyCommand.Path }
    if (-not [string]::IsNullOrWhiteSpace($scriptPath)) {
        try {
            $resolvedScript = (Resolve-Path -LiteralPath $scriptPath -ErrorAction Stop).Path
            $candidate = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $resolvedScript) '..\..') -ErrorAction Stop).Path
            if ((Test-Path -LiteralPath (Join-Path $candidate 'deploy\windows\setup_agent.ps1') -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $candidate 'requirements.txt') -PathType Leaf)) { return $candidate }
        } catch {}
    }
    throw "ProjectRoot could not be determined. Run setup_agent.ps1 from a LabManagement checkout or provide -ProjectRoot."
}

function Get-EnvFileValue {
    param([Parameter(Mandatory=$true)][string]$Path,[Parameter(Mandatory=$true)][string]$Name)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $pattern = "^\s*$([regex]::Escape($Name))=(.*)$"
    foreach ($line in Get-Content -LiteralPath $Path -ErrorAction Stop) { if ($line -match $pattern) { return $matches[1].Trim() } }
    return $null
}

function ConvertFrom-SecureValue {
    param([Parameter(Mandatory=$true)][SecureString]$Value)
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    }
}

function Assert-NativeCommandSucceeded {
    param([Parameter(Mandatory=$true)][string]$Description,[int]$ExitCode = $LASTEXITCODE)
    if ($ExitCode -ne 0) { throw "$Description failed with exit code $ExitCode." }
}

function Assert-ValidServerUrl {
    param([Parameter(Mandatory=$true)][string]$Value)
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -notin @('http','https') -or [string]::IsNullOrWhiteSpace($uri.Host)) {
        throw "Server URL must be an absolute HTTP or HTTPS URL, for example http://192.168.1.100:8000."
    }
    return $uri.AbsoluteUri.TrimEnd('/')
}

if (-not (Test-IsAdministrator)) { throw "Administrator rights are required to create and start the SYSTEM auto-start task. Re-open PowerShell as Administrator and run the installer again." }

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Computer Lab Management - Windows Agent Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ProjectRoot = Resolve-ProjectRoot -ExplicitProjectRoot $ProjectRoot
Set-Location -LiteralPath $ProjectRoot
Write-Host "[1/8] Installation directory: $ProjectRoot" -ForegroundColor Green

Write-Host "[2/8] Checking for Python 3.12+..." -ForegroundColor Yellow
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
$pythonArguments = @()
if (-not $pythonCommand) { $pythonCommand = Get-Command python -ErrorAction SilentlyContinue }
if (-not $pythonCommand) {
    $pythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { $pythonCommand = Get-Command py -ErrorAction SilentlyContinue }
    if ($pythonCommand) { $pythonArguments = @('-3') }
}
if (-not $pythonCommand) { throw "Python 3.12 or newer was not found. Install it from https://www.python.org/downloads/windows/ and select 'Add Python to PATH', then run this installer again." }
$pythonExecutable = $pythonCommand.Source
$pythonVersionOutput = & $pythonExecutable @pythonArguments '--version' 2>&1
$pythonExitCode = $LASTEXITCODE
Assert-NativeCommandSucceeded 'Python version check' $pythonExitCode
if ($pythonVersionOutput -notmatch 'Python\s+(\d+)\.(\d+)') { throw "Could not determine the Python version from: $pythonVersionOutput" }
$pythonVersion = [Version]::new([int]$matches[1],[int]$matches[2])
if ($pythonVersion -lt [Version]::new(3,12)) { throw "Python $pythonVersion was found, but LabManagement requires Python 3.12 or newer." }
Write-Host "      Detected: $pythonVersionOutput" -ForegroundColor Green

$VenvDir = Join-Path $ProjectRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
Write-Host "[3/8] Preparing virtual environment: $VenvDir" -ForegroundColor Yellow
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    if (Test-Path -LiteralPath $VenvDir) { throw "The existing virtual environment is incomplete ($VenvPython is missing). Remove only '$VenvDir' and rerun the installer." }
    & $pythonExecutable @pythonArguments '-m' 'venv' $VenvDir
    $venvExitCode = $LASTEXITCODE
    Assert-NativeCommandSucceeded 'Virtual environment creation' $venvExitCode
}
Write-Host '      Virtual environment ready.' -ForegroundColor Green

Write-Host '[4/8] Installing required Python dependencies...' -ForegroundColor Yellow
& $VenvPython '-m' 'pip' 'install' '--upgrade' 'pip' '--quiet'
$pipExitCode = $LASTEXITCODE
Assert-NativeCommandSucceeded 'pip upgrade' $pipExitCode
$requirementsPath = Join-Path $ProjectRoot 'requirements.txt'
if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) { throw "Required dependency file was not found: '$requirementsPath'." }
& $VenvPython '-m' 'pip' 'install' '-r' $requirementsPath '--quiet'
$requirementsExitCode = $LASTEXITCODE
Assert-NativeCommandSucceeded 'requirements installation' $requirementsExitCode
Write-Host '      Dependencies installed successfully.' -ForegroundColor Green

$EnvFile = Join-Path $ProjectRoot 'agent.env'
$existingServerUrl = Get-EnvFileValue -Path $EnvFile -Name 'LAB_SERVER_URL'
$existingSecret = Get-EnvFileValue -Path $EnvFile -Name 'LAB_AGENT_TOKEN'
if ([string]::IsNullOrWhiteSpace($existingSecret)) { $existingSecret = Get-EnvFileValue -Path $EnvFile -Name 'LAB_AGENT_ENROLLMENT_SECRET' }
$existingDryRun = Get-EnvFileValue -Path $EnvFile -Name 'LAB_POWER_DRY_RUN'
if ([string]::IsNullOrWhiteSpace($existingDryRun)) { $existingDryRun = 'true' }

Write-Host '[5/8] Configuring agent connection settings...' -ForegroundColor Yellow
if ($PSBoundParameters.ContainsKey('ServerUrl')) { $finalServerUrl = Assert-ValidServerUrl -Value $ServerUrl }
else {
    $serverPrompt = 'Central server URL (for example http://192.168.1.100:8000)'
    if (-not [string]::IsNullOrWhiteSpace($existingServerUrl)) { $serverPrompt += " [$existingServerUrl]" }
    $enteredServerUrl = Read-Host $serverPrompt
    if ([string]::IsNullOrWhiteSpace($enteredServerUrl)) { $enteredServerUrl = $existingServerUrl }
    if ([string]::IsNullOrWhiteSpace($enteredServerUrl)) { throw 'A central server URL is required.' }
    $finalServerUrl = Assert-ValidServerUrl -Value $enteredServerUrl
}

$plainSecret = $null
try {
    if ($PSBoundParameters.ContainsKey('EnrollmentSecret')) { $plainSecret = ConvertFrom-SecureValue -Value $EnrollmentSecret }
    else {
        $secretPrompt = 'Agent enrollment secret'
        if (-not [string]::IsNullOrWhiteSpace($existingSecret)) { $secretPrompt += ' (press Enter to keep the existing secret)' }
        $enteredSecret = Read-Host $secretPrompt -AsSecureString
        $plainSecret = ConvertFrom-SecureValue -Value $enteredSecret
        if ([string]::IsNullOrWhiteSpace($plainSecret)) { $plainSecret = $existingSecret }
    }
    if ([string]::IsNullOrWhiteSpace($plainSecret)) { throw 'An enrollment secret is required. It was not saved or displayed.' }
    if ($plainSecret -match '[\r\n]') { throw 'The enrollment secret cannot contain a newline.' }
    $agentDataDirectory = Join-Path $ProjectRoot '.lab_management'
    $agentIdPath = Join-Path $agentDataDirectory 'agent_id'
    if (-not (Test-Path -LiteralPath $agentDataDirectory)) { New-Item -ItemType Directory -Path $agentDataDirectory -Force | Out-Null }
    $envContent = @(
        '# Computer Lab Management - Agent Configuration for Windows',
        "LAB_SERVER_URL=$finalServerUrl",
        "LAB_AGENT_TOKEN=$plainSecret",
        "LAB_AGENT_ID_PATH=$agentIdPath",
        'LAB_HEARTBEAT_INTERVAL=5.0',
        "LAB_POWER_DRY_RUN=$existingDryRun",
        'LAB_SCREEN_CAPTURE_INTERVAL=0.5',
        'LAB_SCREEN_IMAGE_QUALITY=70',
        'LAB_SCREEN_MAX_WIDTH=1920',
        'LAB_SCREEN_MAX_HEIGHT=1080',
        'LAB_SCREEN_MAX_FRAME_RATE=2.0'
    )
    Set-Content -LiteralPath $EnvFile -Value $envContent -Encoding UTF8
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $EnvFile '/inheritance:r' '/grant:r' "$currentIdentity`:(F)" '*S-1-5-18:(R)' '*S-1-5-32-544:(F)' | Out-Null
    $envAclExitCode = $LASTEXITCODE
    Assert-NativeCommandSucceeded 'agent.env permission configuration' $envAclExitCode
    & icacls.exe $agentDataDirectory '/inheritance:r' '/grant:r' "$currentIdentity`:(F)" '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
    $dataAclExitCode = $LASTEXITCODE
    Assert-NativeCommandSucceeded 'agent identity directory permission configuration' $dataAclExitCode
} finally { $plainSecret = $null }
Write-Host "      Configuration saved to $EnvFile" -ForegroundColor Green
Write-Host "      LAB_POWER_DRY_RUN remains '$existingDryRun'." -ForegroundColor Green

Write-Host '[6/8] Registering this machine with the central server...' -ForegroundColor Yellow
$healthUrl = "$($finalServerUrl.TrimEnd('/'))/api/health"
try {
    $healthResponse = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10 -ErrorAction Stop
    if ($healthResponse.status -ne 'running') { throw 'Unexpected health response.' }
} catch { throw "The central server is not reachable at $healthUrl. Check the LAN URL, firewall, and server status. Details: $($_.Exception.Message)" }

# Python/httpx logs INFO messages to stderr. Do not merge stderr into the PowerShell
# success stream: PowerShell 5.1/7 can surface those harmless messages as
# NativeCommandError records even when Python exits successfully.
& $VenvPython '-c' 'from agent.main import register; import json; print(json.dumps(register()))' 2>$null
$registrationExitCode = $LASTEXITCODE
Assert-NativeCommandSucceeded 'Agent registration' $registrationExitCode
Write-Host '      Server connection verified and machine registered.' -ForegroundColor Green

Write-Host '[7/8] Configuring Windows auto-start...' -ForegroundColor Yellow
$TaskName = 'LabManagement Agent'
$TaskPath = '\'
$TaskAction = New-ScheduledTaskAction -Execute $VenvPython -Argument '-m agent.main' -WorkingDirectory $ProjectRoot
$TaskTrigger = New-ScheduledTaskTrigger -AtStartup
$TaskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable $true -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$TaskPrincipal = New-ScheduledTaskPrincipal -UserID 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Action $TaskAction -Trigger $TaskTrigger -Settings $TaskSettings -Principal $TaskPrincipal -Force | Out-Null
Write-Host '      Windows scheduled task configured.' -ForegroundColor Green

Write-Host '[8/8] Starting the LabManagement agent...' -ForegroundColor Yellow
Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
Start-Sleep -Seconds 2
$scheduledTask = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
if ($scheduledTask.State -ne 'Running') {
    $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $TaskPath
    throw "The scheduled task did not remain running (state: $($scheduledTask.State), result: $($taskInfo.LastTaskResult))."
}
Write-Host "      Agent task is running and connected to $finalServerUrl." -ForegroundColor Green
Write-Host ''
Write-Host '==========================================================' -ForegroundColor Green
Write-Host '  Installation Complete' -ForegroundColor Green
Write-Host '==========================================================' -ForegroundColor Green
Write-Host "  Installation directory: $ProjectRoot" -ForegroundColor White
Write-Host "  Configuration file:     $EnvFile" -ForegroundColor White
Write-Host "  Scheduled task:         $TaskName" -ForegroundColor White
Write-Host "  Power dry-run mode:     $existingDryRun" -ForegroundColor White
