$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Alembic = Join-Path $Root ".venv\Scripts\alembic.exe"

if (-not (Test-Path $Python)) {
    throw "未找到虚拟环境 Python，请先运行 python -m venv .venv 并安装依赖。"
}

Push-Location $Root
try {
    Write-Host "检查数据库迁移..."
    & $Alembic upgrade head

    Write-Host "写入本地种子数据..."
    & $Python scripts\seed.py

    Write-Host "检查 Redis/Memurai..."
    $redisPort = netstat -ano | Select-String ":6379"
    if (-not $redisPort) {
        Write-Warning "未检测到 6379 端口。请先启动 Memurai/Redis，否则购物车和限流会不可用。"
    }

    Write-Host "启动 FastAPI: http://127.0.0.1:8000/admin"
    & $Python -m uvicorn commerce.main:app --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}
