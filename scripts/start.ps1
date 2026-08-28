$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8787/api/health" -TimeoutSec 2
    if ($health.ok -and $health.studio_version -eq "2.0") {
        Write-Host "Faceless Factory já está ativo em http://127.0.0.1:8787"
        exit 0
    }
    throw "Existe uma versão anterior ativa. Feche a janela antiga antes de iniciar a versão 2.0."
} catch {
    # Nenhuma instância ativa: continue com o diagnóstico e a inicialização.
}

& $pythonExe app.py doctor
if ($LASTEXITCODE -ne 0) {
    throw "O diagnóstico encontrou um problema. Execute .\scripts\setup.ps1."
}

& $pythonExe app.py serve
