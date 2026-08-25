$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

& $pythonExe app.py doctor
if ($LASTEXITCODE -ne 0) {
    throw "O diagnóstico encontrou um problema. Execute .\scripts\setup.ps1."
}

& $pythonExe app.py serve
