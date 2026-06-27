param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$ReleaseRoot = Join-Path $RootDir "release"
$AppDir = Join-Path $ReleaseRoot "SlidesReader"
$RuntimePythonDir = Join-Path $AppDir "runtime\python"
$RuntimePython = Join-Path $RuntimePythonDir "python.exe"
$FrontendDir = Join-Path $RootDir "frontend"
$BackendDir = Join-Path $RootDir "backend"
$BuildDistExe = Join-Path $RootDir "dist\SlidesReader.exe"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-RequiredCommand {
    param(
        [string]$CommandName,
        [string]$InstallHint
    )

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Missing command: ${CommandName}. ${InstallHint}"
    }

    return $command.Source
}

function Invoke-CheckedCommand {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$Description
    )

    $process = Start-Process -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -Wait `
        -PassThru

    if ($process.ExitCode -ne 0) {
        throw "${Description} failed with exit code $($process.ExitCode)."
    }
}

function Copy-DirectoryContents {
    param(
        [string]$SourceDir,
        [string]$DestinationDir,
        [string[]]$ExcludedNames = @(),
        [string[]]$ExcludedRelativePaths = @()
    )

    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $sourceRoot = (Resolve-Path -LiteralPath $SourceDir).Path.TrimEnd('\')
    $items = Get-ChildItem -LiteralPath $SourceDir -Force -Recurse
    foreach ($item in $items) {
        $relativePath = $item.FullName.Substring($sourceRoot.Length).TrimStart('\')
        $relativeParts = $relativePath -split '\\'
        $skip = $false
        foreach ($relativePart in $relativeParts) {
            if ($ExcludedNames -contains $relativePart) {
                $skip = $true
            }
        }

        foreach ($excludedRelativePath in $ExcludedRelativePaths) {
            if ($relativePath -eq $excludedRelativePath -or $relativePath.StartsWith("$excludedRelativePath\")) {
                $skip = $true
            }
        }

        if ($skip) {
            continue
        }

        $target = Join-Path $DestinationDir $relativePath
        if ($item.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $target | Out-Null
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $item.FullName -Destination $target -Force
        }
    }
}

function Copy-PortablePython {
    param(
        [string]$PythonLauncher,
        [string]$DestinationDir
    )

    $pythonPrefix = & $PythonLauncher -3.11 -c "import sys; print(sys.base_prefix)"
    if (-not $pythonPrefix) {
        throw "Could not resolve Python base_prefix."
    }

    if (Test-Path -LiteralPath $DestinationDir) {
        Remove-Item -LiteralPath $DestinationDir -Recurse -Force
    }

    Copy-DirectoryContents -SourceDir $pythonPrefix `
        -DestinationDir $DestinationDir `
        -ExcludedNames @("__pycache__") `
        -ExcludedRelativePaths @("Lib\site-packages")

    $sitePackages = Join-Path $DestinationDir "Lib\site-packages"
    New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null
}

Write-Step "Checking release build commands"
$PythonLauncher = Resolve-RequiredCommand -CommandName "py.exe" -InstallHint "Install Python 3.11+ and enable the Python Launcher."
$NpmCommand = Resolve-RequiredCommand -CommandName "npm.cmd" -InstallHint "Install Node.js 20+."

Write-Step "Cleaning previous release output"
if (Test-Path -LiteralPath $AppDir) {
    Remove-Item -LiteralPath $AppDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

Write-Step "Building frontend"
Invoke-CheckedCommand -FilePath $NpmCommand `
    -ArgumentList @("ci") `
    -WorkingDirectory $FrontendDir `
    -Description "frontend npm ci"
Invoke-CheckedCommand -FilePath $NpmCommand `
    -ArgumentList @("run", "build") `
    -WorkingDirectory $FrontendDir `
    -Description "frontend build"

$FrontendDist = Join-Path $FrontendDir "dist"
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDist "index.html"))) {
    throw "frontend/dist/index.html was not created."
}

Write-Step "Copying release runtime Python"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RuntimePythonDir) | Out-Null
Copy-PortablePython -PythonLauncher $PythonLauncher -DestinationDir $RuntimePythonDir
Invoke-CheckedCommand -FilePath $RuntimePython `
    -ArgumentList @("-m", "ensurepip", "--upgrade") `
    -WorkingDirectory $RootDir `
    -Description "runtime ensurepip"
Invoke-CheckedCommand -FilePath $RuntimePython `
    -ArgumentList @("-m", "pip", "install", "--upgrade", "pip") `
    -WorkingDirectory $RootDir `
    -Description "runtime pip upgrade"

Write-Step "Copying runtime files"
Copy-DirectoryContents -SourceDir $BackendDir `
    -DestinationDir (Join-Path $AppDir "backend") `
    -ExcludedNames @(".venv", "__pycache__", ".pytest_cache")

New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "frontend") | Out-Null
Copy-Item -LiteralPath $FrontendDist -Destination (Join-Path $AppDir "frontend\dist") -Recurse
Copy-Item -LiteralPath (Join-Path $RootDir "README.md") -Destination (Join-Path $AppDir "README.md")
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "storage") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "tools\downloads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "tools\libreoffice") | Out-Null

Write-Step "Preparing PyInstaller environment"
$PackagingVenv = Join-Path $ReleaseRoot ".packaging-venv"
$PackagingPython = Join-Path $PackagingVenv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PackagingPython)) {
    Invoke-CheckedCommand -FilePath $PythonLauncher `
        -ArgumentList @("-3.11", "-m", "venv", $PackagingVenv) `
        -WorkingDirectory $RootDir `
        -Description "packaging venv creation"
}
Invoke-CheckedCommand -FilePath $PackagingPython `
    -ArgumentList @("-m", "pip", "install", "--upgrade", "pip", "pyinstaller") `
    -WorkingDirectory $RootDir `
    -Description "PyInstaller installation"

Write-Step "Building SlidesReader.exe"
Invoke-CheckedCommand -FilePath $PackagingPython `
    -ArgumentList @("-m", "PyInstaller", "--onefile", "--console", "--name", "SlidesReader", "start.py") `
    -WorkingDirectory $RootDir `
    -Description "PyInstaller build"

if (-not (Test-Path -LiteralPath $BuildDistExe)) {
    throw "dist/SlidesReader.exe was not created."
}
Copy-Item -LiteralPath $BuildDistExe -Destination (Join-Path $AppDir "SlidesReader.exe") -Force

Write-Step "Release build complete"
Write-Host "Version: ${Version}" -ForegroundColor Green
Write-Host "Directory: ${AppDir}" -ForegroundColor Green
Write-Host "Start: double-click release\SlidesReader\SlidesReader.exe" -ForegroundColor Green
