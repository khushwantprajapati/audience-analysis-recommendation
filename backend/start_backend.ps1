param(
    [int]$Port = 8000
)

Set-Location $PSScriptRoot
Write-Host "Starting backend on port $Port..." -ForegroundColor Green

$conflictPattern = '^(<<<<<<<|=======|>>>>>>>|>>>>main|>>>>\s*main)$'
$conflicts = Get-ChildItem -Path "$PSScriptRoot/app" -Recurse -File -Include *.py |
    Select-String -Pattern $conflictPattern

if ($conflicts) {
    Write-Host "" 
    Write-Host "[ERROR] Merge conflict markers were found in backend Python files." -ForegroundColor Red
    Write-Host "Please resolve these before starting the backend:" -ForegroundColor Yellow
    $conflicts | ForEach-Object {
        Write-Host (" - {0}:{1}: {2}" -f $_.Path, $_.LineNumber, $_.Line.Trim()) -ForegroundColor Yellow
    }
    Write-Host "" 
    Write-Host "Tip: Open the file and remove leftover markers like <<<<<<<, =======, >>>>>>>." -ForegroundColor Cyan
    exit 1
}

uvicorn app.main:app --reload --port $Port
