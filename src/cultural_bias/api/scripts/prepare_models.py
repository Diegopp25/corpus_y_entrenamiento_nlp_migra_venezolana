"""Descarga y prepara los pesos BETO en despliegues (Railway, Render, HF Spaces).

Los pesos (~440 MB por modelo) no viven en el repositorio. Para un despliegue
con modelos reales se sube un ZIP con las carpetas ``modelo_sentimiento`` y
``modelo_encuadre`` (o ``bert-sentiment`` y ``bert-frames``) a un GitHub
Release / Hugging Face y se configura:

    NLP_MODELS_ARCHIVE_URL=https://.../modelos_beto.zip   (ZIP o .tar.gz)
    NLP_MODELS_DIR=/app/models                            (carpeta destino)
    NLP_REQUIRE_MODELS=true                               (fallar si no se puede)

El script descarga, extrae de forma segura y deja las carpetas como
``bert-sentiment/`` y ``bert-frames/``, exportando
``NLP_SENTIMENT_MODEL_DIR`` y ``NLP_FRAMES_MODEL_DIR`` para que el motor real
las encuentre. Si no hay URL configurada, no hace nada y el API sigue con el
motor léxico (degradado) para que el servicio siempre arranque.
"""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin", "model.pt")
TOKENIZER_FILES = ("tokenizer.json", "vocab.txt")

SENTIMENT_HINTS = ("modelo_sentimiento", "bert-sentiment", "sentiment", "sentimiento")
FRAMES_HINTS = ("modelo_encuadre", "bert-frames", "frames", "encuadre")


def log(message: str) -> None:
    print(f"[modelos] {message}", flush=True)


def _is_model_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    has_weights = any((path / name).exists() for name in WEIGHT_FILES)
    has_tokenizer = any((path / name).exists() for name in TOKENIZER_FILES)
    return has_weights and has_tokenizer


def models_ready(models_dir: Path) -> bool:
    return _is_model_dir(models_dir / "bert-sentiment") and _is_model_dir(
        models_dir / "bert-frames"
    )


def download(url: str, destination: Path, timeout: int = 900) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "MigraVenezuelaAPI/1.0 (+deploy)"}
    )
    log(f"descargando pesos desde {url}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        next_report = 50 * 1024 * 1024
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if downloaded >= next_report:
                    if total:
                        log(
                            f"descargados {downloaded / 1e6:.0f} MB de "
                            f"{total / 1e6:.0f} MB"
                        )
                    else:
                        log(f"descargados {downloaded / 1e6:.0f} MB")
                    next_report += 50 * 1024 * 1024
    log(f"descarga completada ({downloaded / 1e6:.0f} MB)")


def _safe_extract(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    target_resolved = target.resolve()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                destination = (target / member.filename).resolve()
                if not str(destination).startswith(str(target_resolved)):
                    raise RuntimeError(f"Entrada insegura en el ZIP: {member.filename}")
            bundle.extractall(target)
        return
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                destination = (target / member.name).resolve()
                if not str(destination).startswith(str(target_resolved)):
                    raise RuntimeError(f"Entrada insegura en el TAR: {member.name}")
            bundle.extractall(target)
        return
    raise RuntimeError("El archivo descargado no es ZIP ni TAR")


def _candidate_dirs(root: Path, hints: tuple[str, ...]) -> list[Path]:
    """Busca carpetas que parezcan un modelo guardado con ``save_pretrained``."""
    candidates = [
        path
        for path in root.rglob("*")
        if _is_model_dir(path)
    ]
    if not candidates:
        return []
    preferred = [
        path for path in candidates if any(hint in path.name.lower() for hint in hints)
    ]
    ordered = preferred + [path for path in candidates if path not in preferred]
    ordered.sort(key=lambda path: len(path.parts))
    return ordered


def _place(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    log(f"modelo preparado en {destination}")


def prepare_models() -> bool:
    """Devuelve True si hay modelos reales disponibles tras la preparación."""
    models_dir = Path(os.environ.get("NLP_MODELS_DIR", "/app/models"))
    if models_ready(models_dir):
        log(f"modelos ya presentes en {models_dir}")
    else:
        archive_url = os.environ.get("NLP_MODELS_ARCHIVE_URL", "").strip()
        archive_path_env = os.environ.get("NLP_MODELS_ARCHIVE_PATH", "").strip()
        if not archive_url and not archive_path_env:
            log(
                "NLP_MODELS_ARCHIVE_URL/NLP_MODELS_ARCHIVE_PATH no están "
                "configuradas: se usará el motor léxico (análisis degradado, el "
                "servicio arranca igual)."
            )
            return False
        models_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="beto-") as tmp:
            tmp_path = Path(tmp)
            if archive_path_env:
                archive = Path(archive_path_env)
                if not archive.exists():
                    log(f"ERROR: no existe NLP_MODELS_ARCHIVE_PATH={archive}")
                    return False
                log(f"usando archivo local de pesos: {archive}")
            else:
                archive = tmp_path / "models.download"
                try:
                    download(archive_url, archive)
                except (urllib.error.URLError, OSError) as exc:
                    log(f"ERROR descargando modelos: {exc}")
                    return False
            extracted = tmp_path / "extracted"
            try:
                _safe_extract(archive, extracted)
            except (OSError, RuntimeError) as exc:
                log(f"ERROR extrayendo modelos: {exc}")
                return False

            sentiment_dirs = _candidate_dirs(extracted, SENTIMENT_HINTS)
            frames_dirs = _candidate_dirs(extracted, FRAMES_HINTS)
            if not sentiment_dirs or not frames_dirs:
                # Buscar por tamaño/nombre de forma más laxa: dos carpetas modelo.
                all_dirs = _candidate_dirs(extracted, tuple())
                log(
                    "No se identificaron claramente las dos carpetas de modelo; "
                    f"candidatas: {[str(path) for path in all_dirs]}"
                )
                return False
            sentiment_dir = sentiment_dirs[0]
            frames_dir = next(
                (path for path in frames_dirs if path != sentiment_dir), None
            )
            if frames_dir is None:
                log("El ZIP solo contiene una de las dos carpetas de modelo.")
                return False
            _place(sentiment_dir, models_dir / "bert-sentiment")
            _place(frames_dir, models_dir / "bert-frames")

    os.environ.setdefault(
        "NLP_SENTIMENT_MODEL_DIR", str(models_dir / "bert-sentiment")
    )
    os.environ.setdefault("NLP_FRAMES_MODEL_DIR", str(models_dir / "bert-frames"))
    os.environ.setdefault("NLP_ENGINE", "bert_pair")
    log(
        "modelos listos: "
        f"{os.environ['NLP_SENTIMENT_MODEL_DIR']} y "
        f"{os.environ['NLP_FRAMES_MODEL_DIR']}"
    )
    return True


def main() -> int:
    prepared = prepare_models()
    require = os.environ.get("NLP_REQUIRE_MODELS", "").strip().lower()
    if not prepared and require in {"1", "true", "yes", "si", "sí"}:
        log(
            "NLP_REQUIRE_MODELS está activo y no se pudieron preparar los "
            "modelos; se cancela el arranque."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
