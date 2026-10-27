$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv and install requirements-dev.txt first.' }
Push-Location -LiteralPath $taskRoot
try {
    & $taskPython -m PyInstaller --noconfirm --distpath dist --workpath build Cosfolio.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
    & $taskPython tools/package_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Portable resource packaging failed.' }
} finally { Pop-Location }
