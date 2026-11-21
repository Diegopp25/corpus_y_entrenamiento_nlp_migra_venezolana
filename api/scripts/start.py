"""Punto de entrada para despliegues: prepara modelos y arranca uvicorn.

Railway/Render/Linux en general:

    python scripts/start.py

Lee ``PORT`` (Railway la inyecta) y escucha en ``0.0.0.0``. Si
``NLP_MODELS_ARCHIVE_URL`` está configurada, descarga los pesos BETO antes de
arrancar; si no, el API arranca igual con el motor léxico de respaldo.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_models import main as prepare_models  # noqa: E402


def main() -> int:
    exit_code = prepare_models()
    if exit_code:
        return exit_code

    host = os.environ.get("HOST", "0.0.0.0")
    port = os.environ.get("PORT", "8000")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--proxy-headers",
        # En un solo argumento para que el comodín no se expanda como archivos
        # al ejecutarse desde algunos shells de Windows.
        "--forwarded-allow-ips=*",
    ]
    print(f"[start] arrancando API en http://{host}:{port}", flush=True)
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
