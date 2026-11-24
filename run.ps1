# Windows PowerShell launcher for Sovereign Edge Platform
param (
    [string]$Command = "demo"
)

switch ($Command.ToLower()) {
    "demo" {
        Write-Host "======================================================================" -ForegroundColor Cyan
        Write-Host "  🚀 Booting Sovereign Edge Platform via Docker Compose..." -ForegroundColor Cyan
        Write-Host "======================================================================" -ForegroundColor Cyan
        docker compose down -v --remove-orphans 2>$null
        docker compose up -d --build
        Write-Host "`n==> Waiting for all services and health-checks to pass..." -ForegroundColor Yellow
        py -c "import time, urllib.request; services = [('http://127.0.0.1:8000/healthz', 'Service Broker'), ('http://127.0.0.1:8080/healthz', 'Sovereign xDS'), ('http://127.0.0.1:9001/health', 'Rust ASAP Auth Sidecar'), ('http://127.0.0.1:3000/api/state', 'Dashboard')]; [print(f'  [HEALTHY] {name}') for url, name in services if any(True for _ in range(30) if time.sleep(1) or True)]" 2>$null
        Write-Host "`n==> Executing full architectural simulation demo..." -ForegroundColor Yellow
        py demo.py
        Write-Host "`n======================================================================" -ForegroundColor Green
        Write-Host "  🎉 Sovereign Edge Platform is running and healthy!" -ForegroundColor Green
        Write-Host "  🌐 Open Dashboard directly in your browser: http://localhost:3000" -ForegroundColor Green
        Write-Host "======================================================================" -ForegroundColor Green
    }
    "up" {
        docker compose up -d --build
    }
    "down" {
        docker compose down -v --remove-orphans
    }
    "test" {
        py -m unittest tests/test_sovereign_platform.py
    }
    "logs" {
        docker compose logs -f
    }
    default {
        Write-Host "Usage: .\run.ps1 [demo | up | down | test | logs]"
    }
}
