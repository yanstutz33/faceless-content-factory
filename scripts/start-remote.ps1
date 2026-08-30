$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
$cloudflaredPath = if ($cloudflared) { $cloudflared.Source } else { "C:\Program Files (x86)\cloudflared\cloudflared.exe" }

if (-not (Test-Path -LiteralPath $cloudflaredPath)) {
    throw "Cloudflared não está instalado. Execute winget install --id Cloudflare.cloudflared --exact."
}

$remoteState = & $pythonExe -c "from pathlib import Path; from factory.config import Settings; s=Settings.load(Path.cwd()); print('ready' if s.remote_access and s.remote_username and len(s.remote_password) >= 16 else 'blocked')"
if ($remoteState -ne "ready") {
    throw "Configure FACTORY_REMOTE_ACCESS=true, FACTORY_REMOTE_USERNAME e uma senha de pelo menos 16 caracteres no .env."
}

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8787/api/health" -TimeoutSec 2
    if (-not $health.remote_access.enabled -or -not $health.remote_access.protected) {
        throw "Reinicie o Hub com a configuração remota protegida antes de abrir o túnel."
    }
} catch {
    throw "Inicie primeiro o Hub com .\scripts\start.ps1 e confirme que o acesso remoto protegido está ativo."
}

Write-Host "Abrindo um endereço HTTPS temporário protegido para o FFactory..."
Write-Host "Mantenha esta janela aberta. Para um endereço permanente, configure um túnel nomeado no Cloudflare Access."
& $cloudflaredPath tunnel --url http://127.0.0.1:8787 --no-autoupdate
