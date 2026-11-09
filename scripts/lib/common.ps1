# Shared helpers for setup.ps1 and start.ps1. Compatible with Windows PowerShell 5.1 and PowerShell 7.

$script:Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$script:BackendDir = Join-Path $script:Root 'backend'
$script:FrontendDir = Join-Path $script:Root 'frontend'
$script:VenvPython = Join-Path $script:BackendDir '.venv\Scripts\python.exe'
$script:EnvFile = Join-Path $script:Root '.env'
$script:DbContainer = 'lexirag-db'

function Write-Step([string]$Message) { Write-Host "`n> $Message" -ForegroundColor White }
function Write-Ok([string]$Message) { Write-Host "  [ok]   $Message" -ForegroundColor Green }
function Write-Info([string]$Message) { Write-Host "  [..]   $Message" -ForegroundColor Gray }
function Write-Warn([string]$Message) { Write-Host "  [warn] $Message" -ForegroundColor Yellow }

function Fail([string]$Message, [string]$Hint = '') {
    Write-Host "  [fail] $Message" -ForegroundColor Red
    if ($Hint) { Write-Host "         $Hint" -ForegroundColor Yellow }
    exit 1
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Read-DotEnv {
    $values = @{}
    if (-not (Test-Path $script:EnvFile)) { return $values }
    foreach ($line in [IO.File]::ReadAllLines($script:EnvFile)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $idx = $trimmed.IndexOf('=')
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim().Trim('"').Trim("'")
        $values[$key] = $value
    }
    return $values
}

function Get-EnvValue([hashtable]$Env, [string]$Key, [string]$Default) {
    if ($Env.ContainsKey($Key) -and $Env[$Key]) { return $Env[$Key] }
    return $Default
}

function Find-Python {
    # Prefer 3.13 (the supported version); accept 3.12 with a warning.
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3.13') },
        @{ Exe = 'python3.13'; Args = @() },
        @{ Exe = 'python'; Args = @() },
        @{ Exe = 'python3'; Args = @() },
        @{ Exe = 'py'; Args = @('-3.12') }
    )
    foreach ($c in $candidates) {
        if (-not (Test-Command $c.Exe)) { continue }
        $version = & $c.Exe @($c.Args + @('-c', "import sys; print('%d.%d' % sys.version_info[:2])")) 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $version) { continue }
        $version = "$version".Trim()
        if ($version -eq '3.13' -or $version -eq '3.12') {
            return @{ Exe = $c.Exe; Args = $c.Args; Version = $version }
        }
    }
    return $null
}

function Test-DockerRunning {
    & docker info --format '{{.ServerVersion}}' *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Docker {
    if (-not (Test-Command 'docker')) {
        Fail 'Docker is not installed.' 'Install Docker Desktop: https://www.docker.com/products/docker-desktop/'
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'Docker Compose v2 is not available.' 'Update Docker Desktop to a recent version.' }

    if (Test-DockerRunning) { Write-Ok 'Docker engine is running'; return }

    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $desktop) {
        Write-Info 'Docker engine is not running; starting Docker Desktop...'
        Start-Process -FilePath $desktop | Out-Null
        for ($i = 0; $i -lt 90; $i++) {
            Start-Sleep -Seconds 2
            if (Test-DockerRunning) { Write-Ok 'Docker engine is running'; return }
        }
    }
    Fail 'Docker engine is not running.' 'Start Docker Desktop, wait until it reports "Engine running", then re-run this script.'
}

function Test-PortListening([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conns
}

function Get-PortOwner([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return '' }
    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    if ($proc) { return "$($proc.ProcessName) (PID $($proc.Id))" }
    return "PID $($conn.OwningProcess)"
}

function Test-DbContainerRunning {
    $state = & docker inspect -f '{{.State.Running}}' $script:DbContainer 2>$null
    return ($LASTEXITCODE -eq 0 -and "$state".Trim() -eq 'true')
}

function Start-Database([hashtable]$Env) {
    $port = [int](Get-EnvValue $Env 'POSTGRES_PORT' '5433')
    if (-not (Test-DbContainerRunning) -and (Test-PortListening $port)) {
        Fail "Port $port is already in use by $(Get-PortOwner $port)." "Set a free POSTGRES_PORT in .env (for example 5434) and re-run."
    }
    Push-Location $script:Root
    try {
        & docker compose up -d db
        if ($LASTEXITCODE -ne 0) { Fail 'docker compose up failed.' 'See the Docker output above.' }
    } finally { Pop-Location }

    Write-Info 'Waiting for PostgreSQL to become healthy...'
    for ($i = 0; $i -lt 60; $i++) {
        $health = & docker inspect -f '{{.State.Health.Status}}' $script:DbContainer 2>$null
        if ("$health".Trim() -eq 'healthy') { Write-Ok "PostgreSQL + pgvector is healthy on 127.0.0.1:$port"; return }
        Start-Sleep -Seconds 2
    }
    Fail 'PostgreSQL did not become healthy in time.' "Inspect logs with: docker compose logs db"
}

function Invoke-Migrations {
    Push-Location $script:BackendDir
    try {
        & $script:VenvPython -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { Fail 'Database migrations failed.' 'Check the database credentials in .env.' }
    } finally { Pop-Location }
    Write-Ok 'Database schema is up to date'
}
