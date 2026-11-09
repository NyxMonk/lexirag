#Requires -Version 5.1
<#
.SYNOPSIS
    Start LexiRAG locally on Windows: database, API and web app.
.DESCRIPTION
    Ensures the Docker database is running and migrated, then runs the FastAPI
    backend and the Vite frontend in this console. Press Ctrl+C to stop both.
    The database container keeps running (data is preserved); stop it with
    `docker compose stop`.
.EXAMPLE
    .\scripts\start.ps1
#>
[CmdletBinding()]
param(
    # Disable uvicorn auto-reload.
    [switch]$NoReload
)

# Native tools write progress to stderr; failures are detected through $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lib\common.ps1')

Write-Host ''
Write-Host 'Starting LexiRAG' -ForegroundColor White

Write-Step 'Checking installation'
if (-not (Test-Path $EnvFile)) { Fail '.env not found.' 'Run .\scripts\setup.ps1 first.' }
if (-not (Test-Path $VenvPython)) { Fail 'Backend virtual environment not found.' 'Run .\scripts\setup.ps1 first.' }
if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) { Fail 'Frontend dependencies not installed.' 'Run .\scripts\setup.ps1 first.' }
if (-not (Test-Command 'npm.cmd')) { Fail 'npm was not found.' 'Install Node.js 20 LTS or newer.' }
Write-Ok 'Installation found'

$envValues = Read-DotEnv
$backendHost = Get-EnvValue $envValues 'BACKEND_HOST' '127.0.0.1'
$backendPort = [int](Get-EnvValue $envValues 'BACKEND_PORT' '8000')
$frontendPort = [int](Get-EnvValue $envValues 'FRONTEND_PORT' '5173')

foreach ($p in @($backendPort, $frontendPort)) {
    if (Test-PortListening $p) {
        Fail "Port $p is already in use by $(Get-PortOwner $p)." 'Stop that process, or change BACKEND_PORT / FRONTEND_PORT in .env (update VITE_API_BASE_URL and CORS_ORIGINS to match).'
    }
}
Write-Ok "Ports $backendPort and $frontendPort are free"

Ensure-Docker
Write-Step 'Starting database'
Start-Database $envValues
Write-Step 'Applying database migrations'
Invoke-Migrations

Push-Location $BackendDir
try { & $VenvPython -m app.cli models-status *> $null; $modelsReady = ($LASTEXITCODE -eq 0) } finally { Pop-Location }
if (-not $modelsReady) { Write-Warn 'Retrieval models are not downloaded; uploads will fail to process. Run: .\scripts\setup.ps1 -DownloadModels' }

Write-Step 'Starting services'
$uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--host', $backendHost, '--port', "$backendPort")
if (-not $NoReload) { $uvicornArgs += '--reload' }

$backend = Start-Process -FilePath $VenvPython -ArgumentList $uvicornArgs -WorkingDirectory $BackendDir -NoNewWindow -PassThru
$frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run', 'dev') -WorkingDirectory $FrontendDir -NoNewWindow -PassThru

function Stop-Tree($proc) {
    if ($proc -and -not $proc.HasExited) {
        & taskkill.exe /PID $proc.Id /T /F *> $null
    }
}

try {
    $apiUrl = "http://localhost:$backendPort"
    $probeHost = if ($backendHost -eq '0.0.0.0') { '127.0.0.1' } else { $backendHost }
    $probeUrl = "http://${probeHost}:$backendPort"
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ($backend.HasExited) { break }
        try {
            # Probe the bound IPv4 address directly: "localhost" may try ::1 first and time out.
            $r = Invoke-WebRequest -Uri "$probeUrl/api/v1/health" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { Fail 'The backend did not start.' 'See the errors above.' }

    Write-Host ''
    Write-Host '  LexiRAG is running' -ForegroundColor Green
    Write-Host "  App        http://localhost:$frontendPort" -ForegroundColor White
    Write-Host "  API        $apiUrl" -ForegroundColor White
    Write-Host "  API docs   $apiUrl/docs" -ForegroundColor White
    Write-Host '  Press Ctrl+C to stop.' -ForegroundColor Gray
    Write-Host ''

    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($backend.HasExited) { Write-Warn 'The backend stopped.' }
    if ($frontend.HasExited) { Write-Warn 'The frontend stopped.' }
} finally {
    Write-Host ''
    Write-Info 'Stopping backend and frontend...'
    Stop-Tree $backend
    Stop-Tree $frontend
    Write-Ok 'Stopped. The database keeps running; stop it with: docker compose stop'
}
