# Run Alembic Database Migrations (PowerShell)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host ">>> Running Database Migrations (Alembic)..." -ForegroundColor Cyan

if (Test-Path ".venv\Scripts\alembic.exe") {
    $AlembicExe = ".venv\Scripts\alembic.exe"
} else {
    $AlembicExe = "alembic"
}

& $AlembicExe upgrade head
