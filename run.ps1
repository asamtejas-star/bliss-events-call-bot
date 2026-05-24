# Start the Bliss AI phone call server
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "Create .env from .env.example first." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
    .\.venv\Scripts\pip install -r requirements.txt
}

Write-Host "Starting server on http://localhost:8000"
Write-Host "In another terminal run: ngrok http 8000"
Write-Host "Then set PUBLIC_BASE_URL in .env to your ngrok https URL."
.\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
