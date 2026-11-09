#Requires -Version 5.1
<#
.SYNOPSIS
    First-time (and repeatable) LexiRAG setup on Windows.
.DESCRIPTION
    Checks prerequisites, creates .env if missing, installs backend and frontend
    dependencies, starts PostgreSQL + pgvector in Docker and applies migrations.
    Safe to run repeatedly; existing configuration is never overwritten.
.EXAMPLE
    .\scripts\setup.ps1
    .\scripts\setup.ps1 -DownloadModels
    .\scripts\setup.ps1 -SkipDatabase
#>
[CmdletBinding()]
param(
    # Install dependencies only; do not start Docker or run migrations.
    [switch]$SkipDatabase,
    # Download the embedding and reranker models (about 4.5 GB, one time).
    [switch]$DownloadModels
)

# Native tools write progress to stderr; failures are detected through $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lib\common.ps1')

Write-Host ''
Write-Host 'LexiRAG setup' -ForegroundColor White
Write-Host "Project: $Root" -ForegroundColor Gray

# -- Prerequisites --------------------------------------------
Write-Step 'Checking prerequisites'

$python = Find-Python
if (-not $python) {
    Fail 'Python 3.13 was not found.' 'Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH") or run: winget install Python.Python.3.13'
}
if ($python.Version -ne '3.13') { Write-Warn "Using Python $($python.Version); 3.13 is the supported version." }
else { Write-Ok "Python $($python.Version)" }

if (-not (Test-Command 'node')) { Fail 'Node.js was not found.' 'Install Node.js 20 LTS or newer: https://nodejs.org/ or run: winget install OpenJS.NodeJS.LTS' }
$nodeVersion = (& node --version).Trim().TrimStart('v')
if ([int]($nodeVersion.Split('.')[0]) -lt 20) { Fail "Node.js $nodeVersion is too old." 'Install Node.js 20 LTS or newer.' }
Write-Ok "Node.js $nodeVersion"

if (-not (Test-Command 'npm')) { Fail 'npm was not found.' 'Reinstall Node.js, which includes npm.' }
Write-Ok "npm $((& npm --version).Trim())"

if (-not $SkipDatabase) { Ensure-Docker }

# -- Environment configuration --------------------------------
Write-Step 'Preparing environment configuration'
if (Test-Path $EnvFile) {
    Write-Ok '.env already exists (left unchanged)'
} else {
    $template = [IO.File]::ReadAllText((Join-Path $Root '.env.example'))
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $password = ([Convert]::ToBase64String($bytes)) -replace '[+/=]', 'x'
    $content = $template -replace '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$password"
    [IO.File]::WriteAllText($EnvFile, $content, (New-Object Text.UTF8Encoding $false))
    Write-Ok 'Created .env from .env.example with a generated database password'
}
$envValues = Read-DotEnv

$storage = Get-EnvValue $envValues 'STORAGE_DIR' 'storage'
if (-not [IO.Path]::IsPathRooted($storage)) { $storage = Join-Path $Root $storage }
New-Item -ItemType Directory -Force -Path $storage | Out-Null
Write-Ok "Document storage: $storage"

# -- Backend --------------------------------------------------
Write-Step 'Installing backend dependencies'
if (-not (Test-Path $VenvPython)) {
    Write-Info 'Creating virtual environment in backend\.venv'
    & $python.Exe @($python.Args + @('-m', 'venv', (Join-Path $BackendDir '.venv')))
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        Fail 'Could not create the Python virtual environment.' 'If the project path is very long, move it to a shorter path (for example C:\dev\lexirag).'
    }
} else {
    Write-Ok 'Virtual environment exists'
}
& $VenvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $BackendDir 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { Fail 'pip install failed.' 'See the pip output above.' }
Write-Ok 'Backend dependencies installed'

# -- Frontend -------------------------------------------------
Write-Step 'Installing frontend dependencies'
$lock = Join-Path $FrontendDir 'package-lock.json'
$installedMarker = Join-Path $FrontendDir 'node_modules\.package-lock.json'
Push-Location $FrontendDir
try {
    if ((Test-Path $installedMarker) -and (Test-Path $lock) -and
        ((Get-Item $installedMarker).LastWriteTime -ge (Get-Item $lock).LastWriteTime)) {
        Write-Ok 'node_modules is up to date'
    } else {
        if (Test-Path $lock) { & npm.cmd ci --no-audit --no-fund } else { & npm.cmd install --no-audit --no-fund }
        if ($LASTEXITCODE -ne 0) { Fail 'npm install failed.' 'See the npm output above.' }
        Write-Ok 'Frontend dependencies installed'
    }
} finally { Pop-Location }

# -- Database -------------------------------------------------
if ($SkipDatabase) {
    Write-Warn 'Skipped database startup and migrations (-SkipDatabase).'
} else {
    Write-Step 'Starting database'
    Start-Database $envValues
    Write-Step 'Applying database migrations'
    Invoke-Migrations
}

# -- Models and OCR --------------------------------------------
Write-Step 'Checking retrieval models'
Push-Location $BackendDir
try {
    & $VenvPython -m app.cli models-status *> $null
    $modelsReady = ($LASTEXITCODE -eq 0)
    if (-not $modelsReady -and $DownloadModels) {
        Write-Info 'Downloading BAAI/bge-m3 and BAAI/bge-reranker-v2-m3 (about 4.5 GB)...'
        & $VenvPython -m app.cli download-models
        if ($LASTEXITCODE -ne 0) { Fail 'Model download failed.' 'Check your internet connection and disk space, then re-run with -DownloadModels.' }
        $modelsReady = $true
    }
} finally { Pop-Location }
if ($modelsReady) { Write-Ok 'Embedding and reranker models are available' }
else { Write-Warn 'Models are not downloaded (about 4.5 GB). Re-run with -DownloadModels to enable document processing and search.' }

if (Test-Command 'tesseract') { Write-Ok 'Tesseract OCR found (scanned pages can be read)' }
else { Write-Warn 'Tesseract OCR not found (optional, for scanned PDFs): winget install UB-Mannheim.TesseractOCR, then add the hin, ben, mar, pan and fra language packs.' }

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host 'Start LexiRAG with:  .\scripts\start.ps1' -ForegroundColor White
Write-Host ''
