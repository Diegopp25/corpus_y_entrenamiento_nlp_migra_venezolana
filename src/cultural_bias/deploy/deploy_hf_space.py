"""Despliega la API en Hugging Face Spaces (Docker) con un solo comando.

Uso:
    # 1) token con permiso de escritura (Settings -> Access Tokens)
    $env:HF_TOKEN = "hf_..."
    .\\api\\.venv\\Scripts\\python.exe deploy\\deploy_hf_space.py

    # Sin pesos BETO (modo léxico, rápido y siempre funciona):
    .\\api\\.venv\\Scripts\\python.exe deploy\\deploy_hf_space.py --no-models

    # Solo preparar la carpeta local, sin subir nada:
    .\\api\\.venv\\Scripts\\python.exe deploy\\deploy_hf_space.py --prepare-only

Script:
1. Crea/actualiza el Space Docker público.
2. Prepara una carpeta con api/ + Dockerfile con torch.
3. Si hay modelos, crea un ZIP con modelo_sentimiento/ y modelo_encuadre/ y lo
   sube dentro del Space; el contenedor lo descomprime al arrancar.
4. Espera a que el Space esté RUNNING e imprime la URL y el /v1/health.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"
DEFAULT_MODELS = [
    Path.home() / "Desktop" / "proyecto" / "modelo_sentimiento",
    Path.home() / "Desktop" / "proyecto" / "modelo_encuadre",
]
COPY_DIRS = ["app", "scripts", "artifacts"]
COPY_FILES = [
    "requirements.txt",
    "requirements-models.txt",
    ".env.example",
]
SPACE_README = """---
title: Migra Venezuela API
emoji: 🗞️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# API de cobertura mediática de la migración venezolana

FastAPI + BETO (sentimiento y 7 encuadres), ingesta de noticias, dashboard y
monitoreo. Documentación interactiva en `/docs`.

Proyecto: https://github.com/Diegopp25/corpus_y_entrenamiento_nlp_migra_venezolana
"""


def log(message: str) -> None:
    print(f"[deploy] {message}", flush=True)


def _ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if (
            name in {".venv", ".venv_gpu", "data", "models", "tests", "__pycache__",
                     ".pytest_cache", ".env", "pyproject.toml", "docker-compose.yml",
                     "Dockerfile", "railway.json", "README.md"}
            or name.startswith("pytest-of-")
            or name.startswith("torchinductor_")
            or name.startswith("pip-")
            or name.endswith(".log")
        ):
            ignored.add(name)
    return ignored


def _copy_api(staging: Path) -> None:
    for directory in COPY_DIRS:
        source = API_DIR / directory
        if source.is_dir():
            shutil.copytree(source, staging / directory, ignore=_ignore, dirs_exist_ok=True)
    for filename in COPY_FILES:
        source = API_DIR / filename
        if source.exists():
            shutil.copy2(source, staging / filename)
    # Artefactos (evaluation/thresholds) ya van en COPY_DIRS; el corpus va
    # dentro de app/resources.
    for cache in staging.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _write_dockerfile(staging: Path, with_models: bool) -> None:
    if with_models:
        dockerfile_name = "Dockerfile.models"
        extra_env = [
            "    NLP_ENGINE=bert_pair",
            "    NLP_DEVICE=cpu",
            "    NLP_MODELS_DIR=/app/models",
            '    NLP_CORS_ORIGINS=["*"]',
            "    NLP_MODELS_ARCHIVE_PATH=/app/models.zip",
            "    NLP_REQUIRE_MODELS=true",
        ]
    else:
        # Space ligero (sin torch): motor léxico, arranca en menos de un minuto.
        dockerfile_name = "Dockerfile"
        extra_env = [
            "    NLP_ENGINE=lexicon",
            "    NLP_DEVICE=cpu",
            '    NLP_CORS_ORIGINS=["*"]',
        ]
    base = (API_DIR / dockerfile_name).read_text(encoding="utf-8")
    # Inserta las variables de despliegue en el ENV del runtime (segundo ENV).
    match = re.search(r"ENV PYTHONDONTWRITEBYTECODE=1 \\\n(?:    .*\n)+", base)
    if not match:
        raise RuntimeError(f"No se pudo insertar ENV en {dockerfile_name}")
    block = match.group(0).rstrip("\n")
    block = block.replace("    PORT=8000", "    PORT=8000 \\\n" + " \\\n".join(extra_env))
    dockerfile = base[: match.start()] + block + base[match.end():]
    if with_models:
        dockerfile = dockerfile.replace(
            'COPY scripts ./scripts',
            'COPY scripts ./scripts\nCOPY models.zip /app/models.zip',
        )
    (staging / "Dockerfile").write_text(dockerfile, encoding="utf-8")


def _make_models_zip(destination: Path, models: list[Path]) -> Path:
    log(f"comprimiendo modelos en {destination} (puede tardar unos minutos)")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as bundle:
        for folder in models:
            if not folder.is_dir():
                raise FileNotFoundError(f"No existe la carpeta de modelo {folder}")
            for path in folder.rglob("*"):
                if path.is_file():
                    bundle.write(path, Path(folder.name) / path.relative_to(folder))
    log(f"ZIP de modelos listo: {destination.stat().st_size / 1e6:.0f} MB")
    return destination


def _prepare_folder(
    temporary_root: Path, with_models: bool, models_zip: Path | None, models: list[Path]
) -> Path:
    staging = temporary_root / "space"
    staging.mkdir(parents=True, exist_ok=True)
    _copy_api(staging)
    _write_dockerfile(staging, with_models=with_models)
    (staging / "README.md").write_text(SPACE_README, encoding="utf-8")
    (staging / ".dockerignore").write_text(
        ".venv/\ndata/\nmodels/\ntests/\n__pycache__/\n*.pyc\n.env\npytest-of-*/\n",
        encoding="utf-8",
    )
    if with_models:
        archive = models_zip or (temporary_root / "models.zip")
        if not models_zip:
            _make_models_zip(archive, models)
        shutil.copy2(archive, staging / "models.zip")
        os.chmod(staging / "models.zip", 0o644)
    return staging


def _space_url(username: str, name: str) -> str:
    slug = f"{username}-{name}".lower().replace("_", "-")
    return f"https://{slug}.hf.space"


def _wait_until_running(api, repo_id: str, timeout: int = 1800) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            runtime = api.get_space_runtime(repo_id=repo_id)
            stage = getattr(runtime, "stage", str(runtime))
            if stage != last:
                log(f"estado del Space: {stage}")
                last = stage
            if stage == "RUNNING":
                return "RUNNING"
            if stage in {"ERROR", "STOPPED", "PAUSED"}:
                return stage
        except Exception as exc:  # pragma: no cover - red/API
            log(f"esperando al Space... ({exc})")
        time.sleep(10)
    return "TIMEOUT"


def _health(url: str, timeout: int = 300) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/v1/health", timeout=20) as response:
                if response.status == 200:
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                pass
        except Exception:
            pass
        time.sleep(10)
    return False


def _read_token(explicit: str) -> str:
    if explicit:
        return explicit.strip()
    for variable in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        value = os.environ.get(variable, "").strip()
        if value:
            return value
    token_file = Path.home() / ".cache" / "huggingface" / "token"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="migra-venezuela-api", help="Nombre del Space")
    parser.add_argument("--token", default="")
    parser.add_argument("--models-zip", type=Path, default=None)
    parser.add_argument(
        "--models-dir",
        type=Path,
        action="append",
        default=None,
        help="Carpeta de modelo (repetible). Por defecto las de Desktop.",
    )
    parser.add_argument("--no-models", action="store_true", help="Desplegar en modo léxico")
    parser.add_argument("--prepare-only", action="store_true", help="Solo preparar carpeta")
    parser.add_argument("--private", action="store_true", help="Space privado (no recomendado)")
    parser.add_argument("--timeout", type=int, default=1800, help="Segundos de espera del build")
    args = parser.parse_args()
    token = _read_token(args.token)

    models = args.models_dir or DEFAULT_MODELS
    with_models = not args.no_models
    if with_models and not args.models_zip:
        missing = [str(path) for path in models if not path.is_dir()]
        if missing:
            log(
                "No se encontraron los modelos en: " + ", ".join(missing) +
                ". Usa --no-models o --models-zip."
            )
            return 2

    temporary_root = Path(tempfile.mkdtemp(prefix="hf-space-"))
    try:
        staging = _prepare_folder(temporary_root, with_models, args.models_zip, models)
        log(f"carpeta preparada en {staging}")

        if args.prepare_only:
            log("--prepare-only: no se sube nada. Revisa la carpeta y el Dockerfile.")
            return 0

        if not token:
            log(
                "Falta el token de Hugging Face. Crea uno en "
                "https://huggingface.co/settings/tokens (permiso write) y define "
                "HF_TOKEN, o pásalo con --token. También puede guardarse en "
                f"{(Path.home() / '.cache' / 'huggingface' / 'token')}."
            )
            return 2

        from huggingface_hub import HfApi

        api = HfApi(token=token)
        whoami = api.whoami()
        username = whoami.get("name") or whoami.get("user")
        if not username:
            log("No se pudo obtener el usuario de Hugging Face desde el token.")
            return 2
        repo_id = f"{username}/{args.name}"
        log(f"creando/actualizando Space {repo_id}")
        api.create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk="docker",
            private=args.private,
            exist_ok=True,
        )
        log("subiendo archivos (los modelos pueden tardar varios minutos)...")
        api.upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=str(staging),
            commit_message="Deploy API Migra Venezuela",
            ignore_patterns=[".venv*", "data/*", "models/*", "tests/*", "__pycache__/*"],
        )
        url = _space_url(username, args.name)
        log(f"Space subido: https://huggingface.co/spaces/{repo_id}")
        log(f"URL pública: {url}")
        log("esperando a que Hugging Face construya y arranque el Space...")
        stage = _wait_until_running(api, repo_id, timeout=args.timeout)
        log(f"estado final: {stage}")
        if stage == "RUNNING":
            if _health(url, timeout=min(300, args.timeout)):
                log(f"OK: API respondiendo en {url}/docs")
            else:
                log(
                    f"El Space está RUNNING pero /v1/health aún no responde; "
                    f"revisa https://huggingface.co/spaces/{repo_id}/logs"
                )
        else:
            log(f"Revisa los logs del Space: https://huggingface.co/spaces/{repo_id}")
        return 0 if stage == "RUNNING" else 1
    finally:
        if not (args.prepare_only or os.environ.get("DEPLOY_KEEP_STAGING")):
            shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
