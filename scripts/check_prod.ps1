$ErrorActionPreference = "Stop"

$BaseUrl = $env:BASE_URL
if (-not $BaseUrl) {
    $BaseUrl = "http://127.0.0.1:8000"
}

$ready = Invoke-WebRequest -Uri "$BaseUrl/health/ready" -UseBasicParsing
Write-Host "Health:" $ready.StatusCode $ready.Content

$ops = Invoke-WebRequest -Uri "$BaseUrl/ops/status" -UseBasicParsing
Write-Host "Ops:" $ops.StatusCode $ops.Content

Write-Host "Production check completed for $BaseUrl"
