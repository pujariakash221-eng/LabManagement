[CmdletBinding()]
param(
    [string]$InstallDirectory = (Join-Path $env:ProgramData "LabManagement"),
    [string]$ServerUrl,
    [SecureString]$EnrollmentSecret,
    [string]$ArchiveUrl = "https://github.com/pujariakash221-eng/LabManagement/archive/refs/heads/main.zip",
    [string]$RepositoryUrl = "https://github.com/pujariakash221-eng/LabManagement.git",
    [string]$RepositorySlug = "pujariakash221-eng/LabManagement",
    [switch]$Update,
    [switch]$NoGit,
    [switch]$SkipElevatedCheck,
    [switch]$SkipSetupHandoff
)

# ==============================================================================
# LabManagement one-command Windows installer
# ==============================================================================
# This bootstrapper installs the LabManagement agent on Windows workstations.
# It automatically detects Git:
#   - If Git is available, it uses the Git-based installation path.
#   - If Git is NOT available, it automatically downloads and extracts the public
#     repository archive from GitHub. Git is not required on target PCs.
#
# Run PowerShell as Administrator:
#   irm https://raw.githubusercontent.com/pujariakash221-eng/LabManagement/main/install-agent.ps1 | iex
# ==============================================================================

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-LabManagementProject {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }
    return (Test-Path -LiteralPath (Join-Path $Path "deploy\windows\setup_agent.ps1") -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $Path "agent\main.py") -PathType Leaf)
}

function Test-LabManagementRepository {
    param([string]$Path)

    return Test-LabManagementProject -Path $Path
}

function Get-CurrentRepositoryRoot {
    param([string]$GitPath)

    if (-not $GitPath) {
        return $null
    }
    $root = & $GitPath -C (Get-Location).Path rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and (Test-LabManagementProject -Path $root)) {
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

function Find-ExtractedProjectRoot {
    param([Parameter(Mandatory = $true)][string]$ExtractPath)

    if (Test-LabManagementProject -Path $ExtractPath) {
        return (Resolve-Path -LiteralPath $ExtractPath).Path
    }
    foreach ($item in (Get-ChildItem -LiteralPath $ExtractPath -Directory -ErrorAction SilentlyContinue)) {
        if (Test-LabManagementProject -Path $item.FullName) {
            return (Resolve-Path -LiteralPath $item.FullName).Path
        }
    }
    $setupFile = Get-ChildItem -LiteralPath $ExtractPath -Filter "setup_agent.ps1" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($setupFile) {
        $candidate = Split-Path -Parent (Split-Path -Parent $setupFile.DirectoryName)
        if (Test-LabManagementProject -Path $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Expand-ProjectArchive {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )

    if (Get-Command Expand-Archive -ErrorAction SilentlyContinue) {
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $DestinationPath -Force -ErrorAction Stop
    } else {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $DestinationPath)
    }
}

function Install-FromArchive {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$TargetDirectory
    )

    $tempRoot = [System.IO.Path]::GetTempPath()
    $tempDir = Join-Path $tempRoot ("LabManagementInstall_" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    try {
        $zipFile = Join-Path $tempDir "archive.zip"
        $extractDir = Join-Path $tempDir "extracted"
        New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12

        Write-Host "Downloading repository archive from: $Url" -ForegroundColor Yellow
        try {
            if ($Url -match "^file://") {
                $filePath = [System.Uri]::new($Url).LocalPath
                Copy-Item -LiteralPath $filePath -Destination $zipFile -Force -ErrorAction Stop
            } elseif ($Url -match "^https?://") {
                Invoke-WebRequest -Uri $Url -OutFile $zipFile -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
            } elseif (Test-Path -LiteralPath $Url) {
                Copy-Item -LiteralPath $Url -Destination $zipFile -Force -ErrorAction Stop
            } else {
                Invoke-WebRequest -Uri $Url -OutFile $zipFile -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop
            }
        } catch {
            throw "Failed to download the LabManagement repository ZIP from $Url. Verify internet connectivity and that the repository is accessible. Details: $($_.Exception.Message)"
        }

        Write-Host "Extracting repository archive..." -ForegroundColor Yellow
        try {
            Expand-ProjectArchive -ZipPath $zipFile -DestinationPath $extractDir
        } catch {
            throw "Failed to extract repository archive from '$zipFile'. Details: $($_.Exception.Message)"
        }

        $sourceRoot = Find-ExtractedProjectRoot -ExtractPath $extractDir
        if (-not $sourceRoot) {
            throw "The downloaded archive does not contain a valid LabManagement project (missing deploy\windows\setup_agent.ps1)."
        }

        Write-Host "Installing project files to: $TargetDirectory" -ForegroundColor Green
        if (-not (Test-Path -LiteralPath $TargetDirectory)) {
            New-Item -ItemType Directory -Path $TargetDirectory -Force | Out-Null
        }

        Get-ChildItem -LiteralPath $sourceRoot -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $TargetDirectory -Recurse -Force
        }

        return (Resolve-Path -LiteralPath $TargetDirectory).Path
    } finally {
        Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $SkipElevatedCheck -and -not (Test-IsAdministrator)) {
    throw "Run this installer from an elevated PowerShell window. Administrator rights are required to install under the selected directory."
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  LabManagement Windows Agent Installer" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$gitPath = $null
if (-not $NoGit) {
    $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    }
    $gitPath = if ($gitCommand) { $gitCommand.Source } else { $null }
}

if ($gitPath) {
    Write-Host "Git detected: $gitPath" -ForegroundColor Green
} else {
    Write-Host "Git was not detected. Git is optional; using public repository archive fallback." -ForegroundColor Yellow
}

# Prefer an explicitly requested installation directory when specified. Otherwise,
# prefer the checked-out repository containing this script, then an existing
# installation directory, then a repository containing the caller's current location.
$isExplicitInstallDir = $PSBoundParameters.ContainsKey("InstallDirectory")
$scriptRepository = if (-not $isExplicitInstallDir -and (Test-LabManagementProject -Path $PSScriptRoot)) {
    (Resolve-Path -LiteralPath $PSScriptRoot).Path
} else {
    $null
}
$targetRepository = if (Test-LabManagementProject -Path $InstallDirectory) {
    (Resolve-Path -LiteralPath $InstallDirectory).Path
} else {
    $null
}
$currentRepository = if (-not $isExplicitInstallDir) { Get-CurrentRepositoryRoot -GitPath $gitPath } else { $null }

$projectRoot = if ($isExplicitInstallDir) {
    $targetRepository
} else {
    if ($scriptRepository) { $scriptRepository } elseif ($targetRepository) { $targetRepository } else { $currentRepository }
}

if ($projectRoot -and -not $Update) {
    Write-Host "Using existing LabManagement installation: $projectRoot" -ForegroundColor Green
} else {
    $parentDirectory = Split-Path -Parent $InstallDirectory
    if ([string]::IsNullOrWhiteSpace($parentDirectory)) {
        throw "InstallDirectory must include a parent directory."
    }
    if (Test-Path -LiteralPath $InstallDirectory) {
        $contents = Get-ChildItem -LiteralPath $InstallDirectory -Force -ErrorAction Stop
        if ($contents.Count -gt 0 -and -not (Test-LabManagementProject -Path $InstallDirectory)) {
            throw "Install directory '$InstallDirectory' already exists but is not a LabManagement installation. Choose an empty directory with -InstallDirectory."
        }
    }
    if (-not (Test-Path -LiteralPath $parentDirectory)) {
        New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
    }

    if ($gitPath) {
        Write-Host "Cloning repository from $RepositoryUrl..." -ForegroundColor Yellow
        $ghCommand = Get-Command gh.exe -ErrorAction SilentlyContinue
        if (-not $ghCommand) {
            $ghCommand = Get-Command gh -ErrorAction SilentlyContinue
        }

        $cloneSucceeded = $false
        if ($ghCommand) {
            & $ghCommand.Source repo clone $RepositorySlug $InstallDirectory 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-LabManagementProject -Path $InstallDirectory)) {
                $cloneSucceeded = $true
            }
        }
        if (-not $cloneSucceeded) {
            & $gitPath clone $RepositoryUrl $InstallDirectory
            Assert-NativeCommandSucceeded "Repository clone"
        }

        if (-not (Test-LabManagementProject -Path $InstallDirectory)) {
            throw "Clone completed but the expected LabManagement setup script was not found at '$InstallDirectory'."
        }
        $projectRoot = (Resolve-Path -LiteralPath $InstallDirectory).Path
        Write-Host "Repository cloned to: $projectRoot" -ForegroundColor Green
    } else {
        $projectRoot = Install-FromArchive -Url $ArchiveUrl -TargetDirectory $InstallDirectory
        if (-not (Test-LabManagementProject -Path $projectRoot)) {
            throw "Installation completed but the expected LabManagement setup script was not found at '$projectRoot'."
        }
        Write-Host "Public repository archive extracted and installed to: $projectRoot" -ForegroundColor Green
    }
}

if (-not $SkipSetupHandoff) {
    $setupScript = Join-Path $projectRoot "deploy\windows\setup_agent.ps1"
    $setupParameters = @{}
    if ($PSBoundParameters.ContainsKey("ServerUrl")) {
        $setupParameters["ServerUrl"] = $ServerUrl
    }
    if ($PSBoundParameters.ContainsKey("EnrollmentSecret")) {
        $setupParameters["EnrollmentSecret"] = $EnrollmentSecret
    }

    # Use exact named parameter binding only. This avoids the PowerShell 5.1
    # positional argument ambiguity during setup.
    & $setupScript -ProjectRoot $projectRoot @setupParameters
}
