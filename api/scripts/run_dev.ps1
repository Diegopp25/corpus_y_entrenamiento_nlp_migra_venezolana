<#
.SYNOPSIS
    Arranca el API de cobertura mediática de la migración venezolana en local.

.DESCRIPTION
    Usa el entorno virtual `api/.venv` si existe; si no, cae al `python` del
    sistema. Carga `api/.env` (si está) como variables de entorno y lanza
    uvicorn con host y puerto configurables. Muestra las URLs de la API, la
    documentación interactiva y el healthcheck.

.PARAMETER BindHost
    Interfaz de escucha. Por defecto 127.0.0.1 (solo local).

.PARAMETER Port
    Puerto HTTP. Por defecto 8000.

.PARAMETER Reload
    Activa la recarga automática (útil mientras se desarrolla).

.PARAMETER Engine
    Fuerza el motor de análisis: auto | bert_pair | multitask | lexicon.
    Sobrescribe NLP_ENGINE del .env solo para este arranque.

.EXAMPLE
    .\scripts\run_dev.ps1

.EXAMPLE
    .\scripts\run_dev.ps1 -Port 8080 -Reload -Engine lexicon
#>
[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload,
    [ValidateSet("auto", "bert_pair", "multitask", "lexicon")]
    [string]$Engine
)

$ErrorActionPreference = "Stop"

$ApiDir = Split-Path -Parent $PSScriptRoot
Push-Location $ApiDir
try {
    # 1) Elegir intérprete: .venv del API si existe; si no, python del sistema.
    $python = Join-Path $ApiDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
        Write-Host "[aviso] No existe api/.venv; se usa el python del sistema." -ForegroundColor Yellow
        Write-Host "        Crea el entorno con: python -m venv .venv" -ForegroundColor DarkGray
    }

    # 2) Cargar .env (pydantic-settings también lo lee, pero así queda visible
    #    para cualquier proceso hijo y para diagnosticar la configuración).
    $envFile = Join-Path $ApiDir ".env"
    if (Test-Path $envFile) {
        Write-Host "[i] Cargando variables desde $envFile" -ForegroundColor DarkGray
        foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
            $trimmed = $line.Trim()
            if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) { continue }
            $separator = $trimmed.IndexOf("=")
            if ($separator -le 0) { continue }
            $name = $trimmed.Substring(0, $separator).Trim()
            $value = $trimmed.Substring($separator + 1).Trim()
            if ($value.Length -ge 2 -and (
                    ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                    ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    else {
        Write-Host "[aviso] No hay api/.env; se usan los valores por defecto (motor léxico)." -ForegroundColor Yellow
        Write-Host "        Copia api/.env.example a api/.env para configurar los modelos." -ForegroundColor DarkGray
    }

    if ($Engine) {
        [Environment]::SetEnvironmentVariable("NLP_ENGINE", $Engine, "Process")
    }

    # 3) Lanzar uvicorn.
    $uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", "$Port")
    if ($Reload) { $uvicornArgs += "--reload" }

    $baseUrl = "http://${BindHost}:${Port}"
    Write-Host ""
    Write-Host "  API ......... $baseUrl" -ForegroundColor Cyan
    Write-Host "  Docs ........ $baseUrl/docs" -ForegroundColor Cyan
    Write-Host "  OpenAPI ..... $baseUrl/openapi.json" -ForegroundColor DarkGray
    Write-Host "  Health ...... $baseUrl/v1/health" -ForegroundColor DarkGray
    Write-Host "  Métricas .... $baseUrl/metrics" -ForegroundColor DarkGray
    Write-Host "  (Ctrl+C para detener)" -ForegroundColor DarkGray
    Write-Host ""

    & $python @uvicornArgs
}
finally {
    Pop-Location
}
