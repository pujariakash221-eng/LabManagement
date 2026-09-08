[CmdletBinding()]
param(
    [string]$InstallDirectory = (Join-Path $env:ProgramData "LabManagement"),
    [string]$ServerUrl,
    [SecureString]$EnrollmentSecret
)

$ErrorActionPreference = "Stop"
$RepositoryUrl = "https://github.com/pujariakash221-eng/LabManagement.git"
$ArchiveUrl = "https://github.com/pujariakash221-eng/LabManagement/archive/refs/heads/main.zip"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-LabManagementRepository {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Path "deploy\windows\setup_agent.ps1") -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $Path "requirements.txt") -PathType Leaf)
}

function Assert-NativeCommandSucceeded {
    param([Parameter(Mandatory = $true)][string]$Description)
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE." }
}

function Get-GitPath {
    $command = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $command) { $command = Get-Command git -ErrorAction SilentlyContinue }
    if ($command) { return $command.Source }
    return $null
}

if (-not (Test-IsAdministrator)) {
    throw "Run this installer from an elevated PowerShell window. Administrator rights are required for the LocalSystem auto-start task."
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  LabManagement Windows Agent Installer" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "This installer is independent of the current PowerShell directory." -ForegroundColor Gray

if ([string]::IsNullOrWhiteSpace($InstallDirectory)) { throw "InstallDirectory cannot be empty." }
$InstallDirectory = [Environment]::ExpandEnvironmentVariables($InstallDirectory)
$InstallDirectory = [System.IO.Path]::GetFullPath($InstallDirectory)

if (Test-LabManagementRepository -Path $InstallDirectory) {
    $projectRoot = (Resolve-Path -LiteralPath $InstallDirectory).Path
    Write-Host "Existing LabManagement installation found: $projectRoot" -ForegroundColor Green
} else {
    if (Test-Path -LiteralPath $InstallDirectory -PathType Container) {
        $contents = @(Get-ChildItem -LiteralPath $InstallDirectory -Force -ErrorAction Stop)
        if ($contents.Count -gt 0) {
            throw "Install directory '$InstallDirectory' already exists and is not a LabManagement installation. Use -InstallDirectory with an empty directory or remove the incomplete installation directory."
        }
    } elseif (Test-Path -LiteralPath $InstallDirectory) {
        throw "Install path '$InstallDirectory' exists but is not a directory. Choose another -InstallDirectory."
    }

    $parentDirectory = Split-Path -Parent $InstallDirectory
    if (-not (Test-Path -LiteralPath $parentDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
    }

    $gitPath = Get-GitPath
    if ($gitPath) {
        Write-Host "Git detected: $gitPath" -ForegroundColor Green
        Write-Host "Cloning the public LabManagement repository..." -ForegroundColor Yellow
        & $gitPath clone --depth 1 $RepositoryUrl $InstallDirectory
        Assert-NativeCommandSucceeded "LabManagement Git clone"
    } else {
        Write-Host "Git was not detected. Using the public GitHub ZIP archive." -ForegroundColor Yellow
        $temporaryRoot = Join-Path $env:TEMP ("LabManagement-install-" + [Guid]::NewGuid().ToString("N"))
        $archivePath = Join-Path $temporaryRoot "LabManagement-main.zip"
        $extractPath = Join-Path $temporaryRoot "extracted"
        try {
            New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
            Invoke-WebRequest -Uri $ArchiveUrl -OutFile $archivePath -UseBasicParsing -ErrorAction Stop
            Expand-Archive -LiteralPath $archivePath -DestinationPath $extractPath -Force
            $extractedRoot = Join-Path $extractPath "LabManagement-main"
            if (-not (Test-LabManagementRepository -Path $extractedRoot)) {
                throw "The downloaded GitHub archive does not contain a valid LabManagement repository."
            }
            New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null
            Get-ChildItem -LiteralPath $extractedRoot -Force | ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination $InstallDirectory -Recurse -Force
            }
        } finally {
            if (Test-Path -LiteralPath $temporaryRoot) {
                Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    if (-not (Test-LabManagementRepository -Path $InstallDirectory)) {
        throw "Installation completed, but the expected LabManagement files were not found at '$InstallDirectory'."
    }
    $projectRoot = (Resolve-Path -LiteralPath $InstallDirectory).Path
    Write-Host "LabManagement installed to: $projectRoot" -ForegroundColor Green
}

$setupScript = Join-Path $projectRoot "deploy\windows\setup_agent.ps1"
if (-not (Test-Path -LiteralPath $setupScript -PathType Leaf)) {
    throw "Agent setup script was not found at '$setupScript'."
}

$setupArguments = @{}
if ($PSBoundParameters.ContainsKey("ServerUrl")) {
    $setupArguments.ServerUrl = $ServerUrl
}
if ($PSBoundParameters.ContainsKey("EnrollmentSecret")) {
    $setupArguments.EnrollmentSecret = $EnrollmentSecret
}

Write-Host "Launching the agent setup engine..." -ForegroundColor Yellow

# Do not invoke setup_agent.ps1 as a .ps1 file. Some college/lab PCs enforce a
# restrictive execution policy through Group Policy, where even a child
# PowerShell -ExecutionPolicy Bypass cannot execute script files. Read the
# trusted setup script from the repository and execute it as a ScriptBlock;
# execution-policy checks for script files do not apply to an in-memory block.
# This does not modify the machine's execution policy.
$setupContent = Get-Content -LiteralPath $setupScript -Raw -ErrorAction Stop
if ([string]::IsNullOrWhiteSpace($setupContent)) {
    throw "The agent setup script is empty: '$setupScript'."
}

try {
    $setupBlock = [ScriptBlock]::Create($setupContent)
    & $setupBlock @setupArguments
} catch {
    throw "LabManagement agent setup failed: $($_.Exception.Message)"
}

if ($LASTEXITCODE -ne 0) {
    throw "LabManagement agent setup failed with exit code $LASTEXITCODE."
}
