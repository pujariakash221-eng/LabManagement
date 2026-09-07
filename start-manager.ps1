[CmdletBinding()]
param(
    [switch]$NoBrowser
)

# ==============================================================================
# LabManagement Windows Manager launcher
# ==============================================================================
# This script intentionally uses the existing ``python -m server.main`` entry
# point. It prepares only the local runtime needed to launch that server; it
# does not change the application's configuration, authentication, or routing.
# ==============================================================================

$ErrorActionPreference = "Stop"

function Write-Stage {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Status,
        [ConsoleColor]$Color = [ConsoleColor]::Green
    )

    Write-Host ("{0}... {1}" -f $Name, $Status) -ForegroundColor $Color
}

function Assert-NativeCommandSucceeded {
    param([Parameter(Mandatory = $true)][string]$Description)

    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Get-PythonCommand {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    $pythonArguments = @()
    if (-not $pythonCommand) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $pythonCommand) {
        $pythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
        }
        if ($pythonCommand) {
            $pythonArguments = @("-3")
        }
    }
    if (-not $pythonCommand) {
        throw "Python 3.12 or newer was not found. Install it from https://www.python.org/downloads/windows/ and select 'Add Python to PATH', then run START_MANAGER.bat again."
    }

    $versionOutput = & $pythonCommand.Source @pythonArguments "--version" 2>&1
    Assert-NativeCommandSucceeded "Python version check"
    if ($versionOutput -notmatch "Python\s+(\d+)\.(\d+)") {
        throw "Could not determine the Python version from: $versionOutput"
    }
    $version = [Version]::new([int]$matches[1], [int]$matches[2])
    if ($version -lt [Version]::new(3, 12)) {
        throw "Python $version was found, but LabManagement requires Python 3.12 or newer."
    }

    return [PSCustomObject]@{
        Path = $pythonCommand.Source
        Arguments = $pythonArguments
        Version = $version
    }
}

function Test-DependenciesAvailable {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    $importCheck = @'
import importlib
import sys

modules = ("fastapi", "httpx", "PIL", "uvicorn", "websockets", "itsdangerous")
failed = False
for module_name in modules:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        failed = True
        print(f"{module_name}: FAIL ({type(exc).__name__}: {exc})")
    else:
        print(f"{module_name}: OK")

sys.exit(1 if failed else 0)
'@

    $pipOutput = & $PythonPath "-m" "pip" "check" 2>&1
    $pipCheckSucceeded = $LASTEXITCODE -eq 0
    if ($pipCheckSucceeded) {
        Write-Host "  pip dependency consistency: OK" -ForegroundColor DarkGreen
    } else {
        Write-Host "  pip dependency consistency: FAIL" -ForegroundColor Red
        $pipOutput | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
    }

    # Supplying the validation program on stdin avoids Windows PowerShell's
    # native-command quote reserialization for a multiline `python -c` value.
    # Python receives the quoted module names exactly as written above.
    $importOutput = $importCheck | & $PythonPath "-" 2>&1
    $importsSucceeded = $LASTEXITCODE -eq 0
    $importOutput | ForEach-Object {
        $color = if ("$_" -match ": OK$") { [ConsoleColor]::DarkGreen } else { [ConsoleColor]::Red }
        Write-Host "  $_" -ForegroundColor $color
    }

    return [PSCustomObject]@{
        Success = $pipCheckSucceeded -and $importsSucceeded
        PipCheckSucceeded = $pipCheckSucceeded
        ImportsSucceeded = $importsSucceeded
    }
}

function Get-RequirementsHash {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-SecureRandomToken {
    param([int]$ByteCount = 48)

    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Set-EnvironmentFileValue {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $pattern = "(?m)^$([regex]::Escape($Name))=.*$"
    if ($Content -notmatch $pattern) {
        throw "The configuration template is missing $Name."
    }
    return [regex]::Replace($Content, $pattern, ("{0}={1}" -f $Name, $Value))
}

function New-ManagerEnvironmentFile {
    param(
        [Parameter(Mandatory = $true)][string]$TemplatePath,
        [Parameter(Mandatory = $true)][string]$EnvironmentPath
    )

    $content = Get-Content -LiteralPath $TemplatePath -Raw -Encoding UTF8
    $content = Set-EnvironmentFileValue -Content $content -Name "LAB_APP_SECRET" -Value (Get-SecureRandomToken -ByteCount 48)
    $content = Set-EnvironmentFileValue -Content $content -Name "LAB_AGENT_ENROLLMENT_SECRET" -Value (Get-SecureRandomToken -ByteCount 48)
    $content = Set-EnvironmentFileValue -Content $content -Name "LAB_INITIAL_ADMIN_PASSWORD" -Value (Get-SecureRandomToken -ByteCount 32)
    Set-Content -LiteralPath $EnvironmentPath -Value $content -Encoding UTF8 -NoNewline

    # New configuration files contain secrets. Restrict them to the creating
    # user plus local administrators and SYSTEM. Existing files are untouched.
    try {
        $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls.exe $EnvironmentPath /inheritance:r /grant:r "${currentUser}:(R,W)" "Administrators:(F)" "SYSTEM:(F)" | Out-Null
        Assert-NativeCommandSucceeded "Configuration file permission setup"
    } catch {
        Write-Warning "Created .env, but could not restrict its Windows ACL automatically: $($_.Exception.Message)"
    }
}

function Read-EnvironmentFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $pair = $trimmed.Split("=", 2)
        $values[$pair[0].Trim()] = $pair[1].Trim()
    }
    return $values
}

function Assert-ManagerConfiguration {
    param([Parameter(Mandatory = $true)][hashtable]$Values)

    $required = @(
        "LAB_SERVER_HOST",
        "LAB_SERVER_PORT",
        "LAB_APP_SECRET",
        "LAB_AGENT_ENROLLMENT_SECRET",
        "LAB_INITIAL_ADMIN_USERNAME",
        "LAB_INITIAL_ADMIN_PASSWORD"
    )
    $missing = @($required | Where-Object { -not $Values.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($Values[$_]) })
    if ($missing.Count -gt 0) {
        throw "The .env file is missing required server settings: $($missing -join ', ')."
    }

    foreach ($secretName in @("LAB_APP_SECRET", "LAB_AGENT_ENROLLMENT_SECRET", "LAB_INITIAL_ADMIN_PASSWORD")) {
        if ($Values[$secretName] -match "^replace-with-") {
            throw "The .env value for $secretName is still a template placeholder. Replace it with a secure value before starting the server."
        }
    }
    if ($Values["LAB_APP_SECRET"].Length -lt 32 -or $Values["LAB_AGENT_ENROLLMENT_SECRET"].Length -lt 24) {
        throw "LAB_APP_SECRET must be at least 32 characters and LAB_AGENT_ENROLLMENT_SECRET at least 24 characters."
    }
    if ($Values["LAB_SERVER_HOST"] -ne "0.0.0.0") {
        throw "LAB_SERVER_HOST must be 0.0.0.0 so lab computers on the LAN can reach the dashboard."
    }

    $port = 0
    if (-not [int]::TryParse($Values["LAB_SERVER_PORT"], [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
        throw "LAB_SERVER_PORT must be a number from 1 to 65535."
    }
    return $port
}

function Set-ServerEnvironmentForChildProcess {
    param([Parameter(Mandatory = $true)][hashtable]$Values)

    $previous = @{}
    foreach ($name in $Values.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $Values[$name], "Process")
    }
    return $previous
}

function Restore-ServerEnvironment {
    param([Parameter(Mandatory = $true)][hashtable]$Previous)

    foreach ($name in $Previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $Previous[$name], "Process")
    }
}

function Test-HealthyServer {
    param([Parameter(Mandatory = $true)][string]$HealthUrl)

    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-PortListeners {
    param([Parameter(Mandatory = $true)][int]$Port)

    $netTcpCommand = Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue
    if ($netTcpCommand) {
        return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            ForEach-Object {
                [PSCustomObject]@{
                    LocalAddress = $_.LocalAddress
                    ProcessId = $_.OwningProcess
                }
            })
    }

    $listeners = @()
    foreach ($line in (& netstat.exe -ano -p TCP)) {
        if ($line -match "^\s*TCP\s+(\S+):$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            $listeners += [PSCustomObject]@{
                LocalAddress = $matches[1]
                ProcessId = [int]$matches[2]
            }
        }
    }
    return $listeners
}

function Get-ListenerDescription {
    param([Parameter(Mandatory = $true)][object[]]$Listeners)

    $descriptions = foreach ($listener in $Listeners) {
        $processName = "unknown"
        try {
            $processName = (Get-Process -Id $listener.ProcessId -ErrorAction Stop).ProcessName
        } catch {
            # The process may exit between the port inspection and this lookup.
        }
        "PID $($listener.ProcessId) ($processName), address $($listener.LocalAddress)"
    }
    return ($descriptions -join "; ")
}

function Get-ManagerLanIPv4Address {
    $networkCommand = Get-Command Get-NetIPAddress -ErrorAction SilentlyContinue
    if ($networkCommand) {
        $address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object {
                $_.IPAddress -notmatch "^(127\.|169\.254\.)" -and
                $_.PrefixOrigin -ne "WellKnown" -and
                $_.AddressState -eq "Preferred"
            } |
            Sort-Object -Property InterfaceMetric |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($address) {
            return $address
        }
    }

    $addressFallback = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
        Where-Object {
            $_.OperationalStatus -eq [System.Net.NetworkInformation.OperationalStatus]::Up -and
            $_.NetworkInterfaceType -ne [System.Net.NetworkInformation.NetworkInterfaceType]::Loopback
        } |
        ForEach-Object { $_.GetIPProperties().UnicastAddresses } |
        Where-Object {
            $_.Address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
            $_.Address.IPAddressToString -notmatch "^169\.254\."
        } |
        Select-Object -First 1
    if ($addressFallback) {
        return $addressFallback.Address.IPAddressToString
    }
    return $null
}

function Show-BackendOutput {
    param(
        [Parameter(Mandatory = $true)][string]$StandardOutputPath,
        [Parameter(Mandatory = $true)][string]$StandardErrorPath
    )

    Write-Host "Recent backend output:" -ForegroundColor Yellow
    $foundOutput = $false
    foreach ($path in @($StandardOutputPath, $StandardErrorPath)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $content = Get-Content -LiteralPath $path -Tail 40 -ErrorAction SilentlyContinue
            if ($content) {
                $foundOutput = $true
                $content | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
            }
        }
    }
    if (-not $foundOutput) {
        Write-Host "  No backend output was written. Check that port is available and review the configuration." -ForegroundColor DarkYellow
    }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  LabManagement Manager" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$environmentPath = Join-Path $projectRoot ".env"
$environmentTemplatePath = Join-Path $projectRoot ".env.example"
$venvDirectory = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"

try {
    if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $projectRoot "server\main.py") -PathType Leaf)) {
        throw "This launcher must be kept in the LabManagement project root. requirements.txt or server\\main.py was not found."
    }

    $python = Get-PythonCommand
    Write-Stage -Name "Checking Python" -Status "OK ($($python.Version))"

    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        if (Test-Path -LiteralPath $venvDirectory) {
            throw "The virtual environment is incomplete ($venvPython is missing). Remove only '$venvDirectory' and run START_MANAGER.bat again."
        }
        & $python.Path @($python.Arguments) "-m" "venv" $venvDirectory
        Assert-NativeCommandSucceeded "Virtual environment creation"
        Write-Stage -Name "Checking virtual environment" -Status "Created"
    } else {
        Write-Stage -Name "Checking virtual environment" -Status "OK"
    }

    $requirementsHash = Get-RequirementsHash -Path $requirementsPath
    $requirementsMarkerPath = Join-Path $venvDirectory ".labmanagement-requirements.sha256"
    $storedRequirementsHash = if (Test-Path -LiteralPath $requirementsMarkerPath -PathType Leaf) { (Get-Content -LiteralPath $requirementsMarkerPath -Raw).Trim() } else { "" }
    $dependencyCheck = Test-DependenciesAvailable -PythonPath $venvPython
    if (-not $dependencyCheck.Success -or $storedRequirementsHash -ne $requirementsHash) {
        Write-Host "Checking dependencies... Installing required packages..." -ForegroundColor Yellow
        & $venvPython "-m" "pip" "install" "-r" $requirementsPath
        Assert-NativeCommandSucceeded "Dependency installation"
        $dependencyCheck = Test-DependenciesAvailable -PythonPath $venvPython
        if (-not $dependencyCheck.Success) {
            throw "Dependencies were installed but could not be validated."
        }
        Set-Content -LiteralPath $requirementsMarkerPath -Value $requirementsHash -Encoding ASCII -NoNewline
        Write-Stage -Name "Checking dependencies" -Status "Installed"
    } else {
        Write-Stage -Name "Checking dependencies" -Status "OK"
    }

    if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
        if (-not (Test-Path -LiteralPath $environmentTemplatePath -PathType Leaf)) {
            throw "Configuration is missing and .env.example could not be found."
        }
        New-ManagerEnvironmentFile -TemplatePath $environmentTemplatePath -EnvironmentPath $environmentPath
        Write-Stage -Name "Checking configuration" -Status "Created .env with secure generated values"
    } else {
        Write-Stage -Name "Checking configuration" -Status "Existing .env preserved"
    }

    $environmentValues = Read-EnvironmentFile -Path $environmentPath
    $port = Assert-ManagerConfiguration -Values $environmentValues
    $healthUrl = "http://127.0.0.1:$port/api/health"
    $dashboardUrl = "http://127.0.0.1:$port/"

    $mutexCreated = $false
    $startupMutex = New-Object System.Threading.Mutex($false, "Local\LabManagementManagerStartup", [ref]$mutexCreated)
    $mutexHeld = $false
    try {
        if (-not $startupMutex.WaitOne([TimeSpan]::FromSeconds(35))) {
            throw "Another LabManagement Manager launcher is still starting. Wait a moment, then run START_MANAGER.bat again."
        }
        $mutexHeld = $true

        if (Test-HealthyServer -HealthUrl $healthUrl) {
            Write-Stage -Name "Checking existing server" -Status "OK (reusing the running LabManagement server)"
            Write-Stage -Name "Health check" -Status "OK"
        } else {
            $listeners = Get-PortListeners -Port $port
            if ($listeners.Count -gt 0) {
                $description = Get-ListenerDescription -Listeners $listeners
                throw "Port $port is already in use by a process that did not answer the LabManagement health check: $description. Stop or reconfigure that application; this launcher will not terminate it."
            }

            $runtimeLogDirectory = Join-Path $projectRoot ".lab_management"
            New-Item -ItemType Directory -Path $runtimeLogDirectory -Force | Out-Null
            $standardOutputPath = Join-Path $runtimeLogDirectory "manager-server.out.log"
            $standardErrorPath = Join-Path $runtimeLogDirectory "manager-server.err.log"
            Remove-Item -LiteralPath $standardOutputPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $standardErrorPath -Force -ErrorAction SilentlyContinue

            $previousEnvironment = Set-ServerEnvironmentForChildProcess -Values $environmentValues
            try {
                $serverProcess = Start-Process -FilePath $venvPython -ArgumentList @("-m", "server.main") -WorkingDirectory $projectRoot -WindowStyle Minimized -RedirectStandardOutput $standardOutputPath -RedirectStandardError $standardErrorPath -PassThru
            } finally {
                Restore-ServerEnvironment -Previous $previousEnvironment
            }
            Write-Stage -Name "Starting server" -Status "Started (PID $($serverProcess.Id))"

            $deadline = (Get-Date).AddSeconds(30)
            $healthy = $false
            while ((Get-Date) -lt $deadline) {
                if (Test-HealthyServer -HealthUrl $healthUrl) {
                    $healthy = $true
                    break
                }
                $serverProcess.Refresh()
                if ($serverProcess.HasExited) {
                    break
                }
                Start-Sleep -Milliseconds 500
            }
            if (-not $healthy) {
                Write-Host "Health check... FAILED" -ForegroundColor Red
                Show-BackendOutput -StandardOutputPath $standardOutputPath -StandardErrorPath $standardErrorPath
                throw "The LabManagement server did not become healthy at $healthUrl within 30 seconds."
            }
            Write-Stage -Name "Health check" -Status "OK"
        }

        $lanAddress = Get-ManagerLanIPv4Address
        Write-Host ""
        Write-Host "Local Dashboard:" -ForegroundColor Cyan
        Write-Host $dashboardUrl -ForegroundColor White
        Write-Host ""
        Write-Host "LAN Dashboard:" -ForegroundColor Cyan
        if ($lanAddress) {
            Write-Host "http://${lanAddress}:$port/" -ForegroundColor White
        } else {
            Write-Host "No active LAN IPv4 address was detected. Connect the manager to the lab network, then run this launcher again." -ForegroundColor Yellow
        }

        if (-not $NoBrowser) {
            Write-Host ""
            Write-Host "Opening dashboard..." -ForegroundColor Cyan
            Start-Process $dashboardUrl
        }
    } finally {
        if ($mutexHeld) {
            $startupMutex.ReleaseMutex()
        }
        $startupMutex.Dispose()
    }
    exit 0
} catch {
    Write-Host ""
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
