# Builds dist\db-unlock.exe, a single self-contained executable.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --quiet -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile `
    --name db-unlock --paths src src\db_unlock\__main__.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

Write-Host "Built $PSScriptRoot\dist\db-unlock.exe"
