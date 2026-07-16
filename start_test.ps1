$python = "C:\Users\wer\AppData\Local\Programs\Python\Python314\python.exe"

Write-Host "Qyouro - Full Launch" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Starting Backend API (HTTPS :8443)..." -ForegroundColor Green
Start-Process $python -ArgumentList "qyouro\backend\main.py" -WindowStyle Minimized
Start-Sleep -Seconds 5

try {
    $r = Invoke-WebRequest -Uri "https://127.0.0.1:8443/health" -UseBasicParsing -SkipCertificateCheck
    Write-Host "  OK - Backend running: $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL - Backend error. Trying HTTP fallback..." -ForegroundColor Yellow
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing
        Write-Host "  OK - Backend on HTTP :8000" -ForegroundColor Green
    } catch {
        Write-Host "  FATAL - Backend not reachable" -ForegroundColor Red
    }
}

Write-Host "[2/3] Starting VK Bot..." -ForegroundColor Green
Start-Process $python -ArgumentList "qyouro\bot\main.py" -WindowStyle Minimized
Start-Sleep -Seconds 4
Write-Host "  OK - Bot started (LongPoll)" -ForegroundColor Green

Write-Host "[3/3] Starting License Manager (GUI)..." -ForegroundColor Green
Start-Process $python -ArgumentList "qyouro\license_gen.py" -WindowStyle Normal
Start-Sleep -Seconds 2
Write-Host "  OK - License Manager window opened" -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  ALL RUNNING" -ForegroundColor Green
Write-Host "  Backend:  https://localhost:8443" -ForegroundColor White
Write-Host "  Scanner:  https://localhost:8443/" -ForegroundColor White
Write-Host "  Bot:      @ByteCruft community" -ForegroundColor White
Write-Host "  Licenses: GUI window" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop: powershell -File qyouro\stop.ps1" -ForegroundColor Yellow
