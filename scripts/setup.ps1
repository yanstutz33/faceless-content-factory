$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r requirements.txt

$portableFfmpeg = Join-Path $projectRoot ".tools\ffmpeg\bin\ffmpeg.exe"
if (-not (Test-Path -LiteralPath $portableFfmpeg) -and -not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
    } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install ffmpeg -y --no-progress
    } else {
        throw "FFmpeg não foi encontrado. Instale FFmpeg e execute este setup novamente."
    }
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
}

& $pythonExe app.py doctor
Write-Host "Setup concluído. Execute .\scripts\start.ps1 para abrir o estúdio."
