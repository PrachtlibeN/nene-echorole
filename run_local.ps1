# run_local.ps1 - Script to run EchoRole backend and frontend locally

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       EchoRole Local Runner            " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Environment file check
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "[1/3] Creating .env from .env.example..." -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
    } else {
        Write-Warning ".env.example not found. Please create .env manually."
    }
} else {
    Write-Host "[1/3] Found existing .env file." -ForegroundColor Green
}

# 2. Setup and run Backend
Write-Host "`n[2/3] Setting up Backend..." -ForegroundColor Yellow
$BackendDir = Join-Path $ScriptDir "backend"
$DataDir = Join-Path $BackendDir "data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

# Resolve python
$PythonCmd = "python"
if (Test-Path (Join-Path $BackendDir ".venv\Scripts\python.exe")) {
    $PythonCmd = (Join-Path $BackendDir ".venv\Scripts\python.exe")
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
}

Write-Host "Applying database migrations..." -ForegroundColor Yellow
Push-Location $BackendDir
try {
    & $PythonCmd -m alembic upgrade head
} catch {
    Write-Warning "Alembic migration failed. Please ensure dependencies are installed (pip install -e .)."
} finally {
    Pop-Location
}

Write-Host "Starting backend server on port 8000..." -ForegroundColor Green
$backendProcess = Start-Process -FilePath $PythonCmd -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $BackendDir -PassThru

# 3. Setup and run Frontend
Write-Host "`n[3/3] Setting up Frontend..." -ForegroundColor Yellow
$FrontendDir = Join-Path $ScriptDir "frontend"
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies (npm install)..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    try {
        npm install
    } finally {
        Pop-Location
    }
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host " EchoRole is running successfully!      " -ForegroundColor Green
Write-Host " - Backend API:  http://127.0.0.1:8000  " -ForegroundColor White
Write-Host " - Frontend UI:  http://localhost:5173  " -ForegroundColor White
Write-Host " Press Ctrl+C in this terminal to stop. " -ForegroundColor Gray
Write-Host "========================================`n" -ForegroundColor Green

try {
    Push-Location $FrontendDir
    npm run dev
} finally {
    Pop-Location
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Write-Host "`nShutting down backend process..." -ForegroundColor Yellow
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "EchoRole stopped." -ForegroundColor Cyan
}
