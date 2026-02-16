param(
    [int]$Port = 8000
)

Set-Location $PSScriptRoot
Write-Host "Starting backend on port $Port..." -ForegroundColor Green

python preflight_check.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

uvicorn app.main:app --reload --port $Port
