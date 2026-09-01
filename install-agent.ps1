[CmdletBinding()]
param(
    [string]$InstallDirectory = (Join-Path $env:ProgramData "LabManagement"),
    [string]$ServerUrl,
    [SecureString]$EnrollmentSecret
)

# ==============================================================================
# LabManagement one-command Windows installer
# ==============================================================================
# This bootstrapper deliberately does not download a private repository from
# raw.githubusercontent.com. It reuses an existing checkout when found, or uses
# authenticated Git/GitHub CLI cloning before handing off to setup_agent.ps1.
#
# Run PowerShell as Administrator. See README.md for the one-line, private-repo
# installation command and GitHub authentication requirements.
# ==============================================================================

$ErrorActionPreference = "Stop"
$RepositoryUrl = "https://github.com/pujariakash221-eng/LabManagement.git"
$RepositorySlug = "pujariakash221-eng/LabManagement"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-LabManagementRepository {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }
    return (Test-Path -LiteralPath (Join-Path $Path ".git")) -and
        (Test-Path -LiteralPath (Join-Path $Path "deploy\windows\setup_agent.ps1"))
}

function Get-CurrentRepositoryRoot {
    param([string]$GitPath)

    if (-not $GitPath) {
        return $null
    }
    $root = & $GitPath -C (Get-Location).Path rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and (Test-LabManagementRepository -Path $root)) {
        return (Resolve-Path -LiteralPath $root).Path
    }
    return $null
}

function Assert-NativeCommandSucceeded {
    param([Parameter(Mandatory = $true)][string]$Description)

    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-IsAdministrator)) {
    throw "Run this installer from an elevated PowerShell window. Administrator rights are required for the LocalSystem auto-start task."
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  LabManagement Windows Agent Installer" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $gitCommand) {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
}
$gitPath = if ($gitCommand) { $gitCommand.Source } else { $null }
if ($gitPath) {
    Write-Host "Git detected: $gitPath" -ForegroundColor Green
} else {
    Write-Host "Git was not detected." -ForegroundColor Yellow
}

# Prefer the checked-out repository containing this script, then an existing
# requested installation directory, then a repository containing the caller's
# current location. None of these depend on the PowerShell working directory.
$scriptRepository = if (Test-LabManagementRepository -Path $PSScriptRoot) {
    (Resolve-Path -LiteralPath $PSScriptRoot).Path
} else {
    $null
}
$targetRepository = if (Test-LabManagementRepository -Path $InstallDirectory) {
    (Resolve-Path -LiteralPath $InstallDirectory).Path
} else {
    $null
}
$currentRepository = Get-CurrentRepositoryRoot -GitPath $gitPath
$projectRoot = $scriptRepository
if (-not $projectRoot) { $projectRoot = $targetRepository }
if (-not $projectRoot) { $projectRoot = $currentRepository }

if ($projectRoot) {
    Write-Host "Using existing LabManagement repository: $projectRoot" -ForegroundColor Green
} else {
    if (-not $gitPath) {
        throw "Git is required to clone the private LabManagement repository. Install Git for Windows from https://git-scm.com/download/win, then rerun this command."
    }

    $parentDirectory = Split-Path -Parent $InstallDirectory
    if ([string]::IsNullOrWhiteSpace($parentDirectory)) {
        throw "InstallDirectory must include a parent directory."
    }
    if (Test-Path -LiteralPath $InstallDirectory) {
        $contents = Get-ChildItem -LiteralPath $InstallDirectory -Force -ErrorAction Stop
        if ($contents.Count -gt 0) {
            throw "Install directory '$InstallDirectory' already exists but is not a LabManagement checkout. Choose an empty directory with -InstallDirectory."
        }
    }
    if (-not (Test-Path -LiteralPath $parentDirectory)) {
        New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
    }

    Write-Host "The LabManagement repository is private; GitHub authentication is required before cloning." -ForegroundColor Yellow
    $ghCommand = Get-Command gh.exe -ErrorAction SilentlyContinue
    if (-not $ghCommand) {
        $ghCommand = Get-Command gh -ErrorAction SilentlyContinue
    }

    if ($ghCommand) {
        & $ghCommand.Source auth status -h github.com 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Opening GitHub CLI authentication. Sign in to an account with repository access." -ForegroundColor Yellow
            & $ghCommand.Source auth login --hostname github.com --git-protocol https --web
            Assert-NativeCommandSucceeded "GitHub CLI authentication"
        }
        & $ghCommand.Source repo clone $RepositorySlug $InstallDirectory
        Assert-NativeCommandSucceeded "Private repository clone"
    } else {
        Write-Host "GitHub CLI was not found. Git will now use Git Credential Manager or its normal secure credential prompt." -ForegroundColor Yellow
        Write-Host "Sign in with a GitHub account or a fine-grained token that has Contents: Read access to $RepositorySlug." -ForegroundColor Yellow
        & $gitPath clone $RepositoryUrl $InstallDirectory
        Assert-NativeCommandSucceeded "Private repository clone"
    }

    if (-not (Test-LabManagementRepository -Path $InstallDirectory)) {
        throw "Clone completed but the expected LabManagement setup script was not found at '$InstallDirectory'."
    }
    $projectRoot = (Resolve-Path -LiteralPath $InstallDirectory).Path
    Write-Host "Private repository cloned to: $projectRoot" -ForegroundColor Green
}

$setupScript = Join-Path $projectRoot "deploy\windows\setup_agent.ps1"
$setupArguments = @{}
if ($PSBoundParameters.ContainsKey("ServerUrl")) {
    $setupArguments.ServerUrl = $ServerUrl
}
if ($PSBoundParameters.ContainsKey("EnrollmentSecret")) {
    $setupArguments.EnrollmentSecret = $EnrollmentSecret
}

# All environment setup, configuration, registration, task creation, startup,
# and connection verification remain in the established setup script.
& $setupScript @setupArguments
