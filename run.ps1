# ROAS Audience Recommendation Engine - One-Click Setup & Launch
# Run: .\run.ps1  (or: powershell -ExecutionPolicy Bypass -File run.ps1)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ROAS Audience Recommendation Engine"       -ForegroundColor Cyan
Write-Host "  One-Click Setup & Launch"                  -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Check / Install Python ────────────────────────────────────────
$pythonOk = $false
try {
    $pyVer = & python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $pyVer" -ForegroundColor Green
        $pythonOk = $true
    }
} catch {}

if (-not $pythonOk) {
    Write-Host "[!] Python not found." -ForegroundColor Yellow
    $hasWinget = Get-Command winget -ErrorAction SilentlyContinue
    if ($hasWinget) {
        Write-Host "[..] Installing Python 3.12 via winget..." -ForegroundColor Yellow
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        try {
            $pyVer = & python --version 2>&1
            Write-Host "[OK] $pyVer (freshly installed)" -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Python installed but not in PATH. Close this terminal, open a new one, and run again." -ForegroundColor Red
            Read-Host "Press Enter to exit"
            exit 1
        }
    } else {
        Write-Host "[ERROR] Install Python 3.10+ from https://python.org (check 'Add to PATH')" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── Check / Install Node.js ──────────────────────────────────────
$nodeOk = $false
try {
    $nodeVer = & node --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Node.js $nodeVer" -ForegroundColor Green
        $nodeOk = $true
    }
} catch {}

if (-not $nodeOk) {
    Write-Host "[!] Node.js not found." -ForegroundColor Yellow
    $hasWinget = Get-Command winget -ErrorAction SilentlyContinue
    if ($hasWinget) {
        Write-Host "[..] Installing Node.js LTS via winget..." -ForegroundColor Yellow
        winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        try {
            $nodeVer = & node --version 2>&1
            Write-Host "[OK] Node.js $nodeVer (freshly installed)" -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Node.js installed but not in PATH. Close this terminal, open a new one, and run again." -ForegroundColor Red
            Read-Host "Press Enter to exit"
            exit 1
        }
    } else {
        Write-Host "[ERROR] Install Node.js 18+ from https://nodejs.org" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── Check pip ─────────────────────────────────────────────────────
try {
    & pip --version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pip failed" }
    Write-Host "[OK] pip available" -ForegroundColor Green
} catch {
    Write-Host "[..] Bootstrapping pip..." -ForegroundColor Yellow
    & python -m ensurepip --upgrade 2>&1 | Out-Null
    try {
        & pip --version 2>&1 | Out-Null
        Write-Host "[OK] pip bootstrapped" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] pip not available. Reinstall Python with pip." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ── Check npm ─────────────────────────────────────────────────────
try {
    & npm --version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "npm failed" }
    Write-Host "[OK] npm available" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] npm not found. Reinstall Node.js from https://nodejs.org" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# ── Backend .env ──────────────────────────────────────────────────
if (-not (Test-Path "backend\.env")) {
    Write-Host "-----------------------------------------------" -ForegroundColor Yellow
    Write-Host " First-time setup: Meta App credentials needed"  -ForegroundColor Yellow
    Write-Host " Get them from https://developers.facebook.com"  -ForegroundColor Yellow
    Write-Host "-----------------------------------------------" -ForegroundColor Yellow
    Write-Host ""
    $metaAppId = Read-Host "  META_APP_ID"
    $metaAppSecret = Read-Host "  META_APP_SECRET"
    Write-Host ""

    $secretKey = "roas-dev-" + (Get-Random -Maximum 999999)
    @"
APP_ENV=development
SECRET_KEY=$secretKey
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
DATABASE_URL=sqlite:///./roas.db
META_APP_ID=$metaAppId
META_APP_SECRET=$metaAppSecret
META_REDIRECT_URI=http://localhost:8000/api/auth/meta/callback
ANTHROPIC_API_KEY=
"@ | Set-Content -Path "backend\.env" -Encoding UTF8
    Write-Host "[OK] Created backend\.env" -ForegroundColor Green
} else {
    Write-Host "[OK] backend\.env exists" -ForegroundColor Green
}

# ── Frontend .env.local ──────────────────────────────────────────
if (-not (Test-Path "frontend\.env.local")) {
    "NEXT_PUBLIC_API_URL=http://localhost:8000" | Set-Content -Path "frontend\.env.local" -Encoding UTF8
    Write-Host "[OK] Created frontend\.env.local" -ForegroundColor Green
} else {
    Write-Host "[OK] frontend\.env.local exists" -ForegroundColor Green
}

# ── Install backend dependencies ─────────────────────────────────
Write-Host ""
Write-Host "[..] Installing backend dependencies..." -ForegroundColor Yellow
Push-Location backend
$ErrorActionPreference = "Continue"
& pip install -r requirements.txt -q 2>&1 | Where-Object { $_ -notmatch "WARNING|DEPRECATION" }
$pipExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($pipExit -ne 0) {
    Write-Host "[ERROR] pip install failed." -ForegroundColor Red
    Pop-Location
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[OK] Backend dependencies ready" -ForegroundColor Green
Pop-Location

# ── Install frontend dependencies ────────────────────────────────
Write-Host "[..] Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location frontend
if (-not (Test-Path "node_modules")) {
    $ErrorActionPreference = "Continue"
    & npm install --silent 2>&1 | Where-Object { $_ -notmatch "warn|WARN" }
    $npmExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($npmExit -ne 0) {
        Write-Host "[ERROR] npm install failed." -ForegroundColor Red
        Pop-Location
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Write-Host "[OK] Frontend dependencies ready" -ForegroundColor Green
Pop-Location

# ── Launch servers ────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Launching servers..."                      -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend:   http://localhost:8000"
Write-Host "  Frontend:  http://localhost:3000"
Write-Host "  API Docs:  http://localhost:8000/docs"
Write-Host ""

# Start backend in new window
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$PSScriptRoot\backend\start_backend.ps1", "-Port", "8000" -WindowStyle Normal

Write-Host "Waiting for backend to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

# Start frontend in new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; Write-Host 'Starting frontend on port 3000...' -ForegroundColor Green; npm run dev" -WindowStyle Normal

Start-Sleep -Seconds 5

# Open browser
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  App is running! Browser should open now." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  - Connect your Meta account from the homepage"
Write-Host "  - Then Sync data and Generate recommendations"
Write-Host ""
Write-Host "  To stop: close the backend and frontend"
Write-Host "           PowerShell windows."
Write-Host ""
Read-Host "Press Enter to exit this setup window"
