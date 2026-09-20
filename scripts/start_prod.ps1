$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Alembic = Join-Path $Root ".venv\Scripts\alembic.exe"
$HostAddress = $env:HOST_ADDRESS
$Port = $env:PORT

if (-not $HostAddress) {
    $HostAddress = "127.0.0.1"
}
if (-not $Port) {
    $Port = "8000"
}
if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run python -m venv .venv and install project dependencies."
}
if (-not (Test-Path ".env")) {
    throw ".env not found. Copy .env.production.example to .env and fill production values first."
}

Push-Location $Root
try {
    New-Item -ItemType Directory -Force -Path "logs" | Out-Null
    New-Item -ItemType Directory -Force -Path "uploads" | Out-Null

    Write-Host "Applying database migrations..."
    & $Alembic upgrade head

    Write-Host "Starting FastAPI on http://$HostAddress`:$Port"
    & $Python -m uvicorn commerce.main:app --host $HostAddress --port $Port --proxy-headers
}
finally {
    Pop-Location
}
