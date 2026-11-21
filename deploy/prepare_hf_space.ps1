# Prepara una carpeta lista para subir como Hugging Face Space (SDK Docker).
#
# Uso (desde la raíz del repo):
#   powershell -ExecutionPolicy Bypass -File deploy\prepare_hf_space.ps1
#
# Deja en $env:USERPROFILE\Desktop\hf-space-migra-api el contenido de api/
# (app, scripts, requirements, artefactos y el Dockerfile con torch) más un
# README con el metadata que exige Hugging Face.

param(
    [string]$SourceApi = (Resolve-Path (Join-Path $PSScriptRoot "..\api")).Path,
    [string]$Destination = (Join-Path $env:USERPROFILE "Desktop\hf-space-migra-api"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path (Join-Path $SourceApi "Dockerfile.models"))) {
    throw "No se encontró api/Dockerfile.models en $SourceApi"
}

if (Test-Path $Destination) {
    if (-not $Force) {
        throw "La carpeta $Destination ya existe. Bórrala o usa -Force."
    }
    Remove-Item $Destination -Recurse -Force
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null

# Copia el contenido de api/ excluyendo lo que no debe ir al Space.
$exclude = @(
    ".venv", "data", "models", ".env", "tests", "pyproject.toml",
    "docker-compose.yml", "Dockerfile", "Dockerfile.models", "railway.json",
    "_tmp", ".pytest_cache", "pytest-of-diego", "torchinductor_diego"
)
Get-ChildItem -Path $SourceApi -Force |
    Where-Object {
        $exclude -notcontains $_.Name -and
        $_.Name -notlike "pytest-of-*" -and
        $_.Name -notlike "torchinductor_*" -and
        $_.Name -notlike "pip-*" -and
        $_.Name -notlike "*.log"
    } |
    ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $Destination -Recurse -Force
    }

# El Space usa el Dockerfile con torch/transformers.
Copy-Item (Join-Path $SourceApi "Dockerfile.models") (Join-Path $Destination "Dockerfile") -Force

# Limpieza de cachés
Get-ChildItem $Destination -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem $Destination -Recurse -File -Include "*.pyc" -ErrorAction SilentlyContinue |
    Remove-Item -Force

$readme = @"
---
title: Migra Venezuela API
emoji: 🗞️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# API de cobertura mediática de la migración venezolana

FastAPI + modelos BETO (sentimiento + 7 encuadres), ingesta de noticias,
dashboard y monitoreo.

- Documentación: https://TU_USUARIO-migra-venezuela-api.hf.space/docs
- Proyecto: https://github.com/Diegopp25/corpus_y_entrenamiento_nlp_migra_venezolana

## Variables necesarias en el Space

- ``NLP_ENGINE=bert_pair``
- ``NLP_MODELS_ARCHIVE_URL`` = URL del ZIP con ``modelo_sentimiento`` y ``modelo_encuadre``
- ``NLP_MODELS_DIR=/app/models``
- ``NLP_REQUIRE_MODELS=true``
- ``NLP_CORS_ORIGINS=["*"]`` (luego pon la URL del frontend)
"@
Set-Content -Path (Join-Path $Destination "README.md") -Value $readme -Encoding UTF8

Write-Host ""
Write-Host "OK: Space preparado en $Destination" -ForegroundColor Green
Write-Host "Siguiente: crea un Space Docker en Hugging Face, clona su repo y copia dentro el contenido de esa carpeta."
Write-Host "No se copiaron .env, models/, data/ ni tests/. Revisa la carpeta antes de subir."
