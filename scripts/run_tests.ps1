# Run Test Suite with Pytest (PowerShell)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host ">>> Running Test Suite..." -ForegroundColor Cyan

if (Test-Path ".venv\Scripts\pytest.exe") {
    $PytestExe = ".venv\Scripts\pytest.exe"
} else {
    $PytestExe = "pytest"
}

& $PytestExe -v
