# Launch FastAPI Development Server (PowerShell)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host ">>> Starting Personal Job Intelligence Platform (Development)..." -ForegroundColor Cyan

# Check for virtual environment
if (Test-Path ".venv\Scripts\python.exe") {
    $PythonExe = ".venv\Scripts\python.exe"
} else {
    $PythonExe = "python"
}

& $PythonExe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
