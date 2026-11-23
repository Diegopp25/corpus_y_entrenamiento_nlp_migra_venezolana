"""Smoke test contra una API desplegada (por defecto la de Azure).

Uso:
    python scripts/check_live_api.py
    LIVE_API_URL=https://mi-api python scripts/check_live_api.py
"""

from __future__ import annotations

import json
import os
import sys

import httpx

BASE_URL = os.environ.get("LIVE_API_URL", "https://20-226-99-99.sslip.io").rstrip("/")
TEXT = (
    "El gobierno anunció un nuevo permiso de residencia para los migrantes "
    "venezolanos que llegaron este año y buscan trabajo."
)


def check(name: str, fn) -> bool:
    try:
        detail = fn()
        print(f"PASS  {name}: {detail}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    print(f"API: {BASE_URL}")
    client = httpx.Client(base_url=BASE_URL, timeout=90)
    ok = True

    def health():
        response = client.get("/v1/health")
        response.raise_for_status()
        body = response.json()
        engine = body["engine"]
        if engine["selected"] != "bert_pair" or engine["degraded"]:
            raise AssertionError(f"motor inesperado: {engine}")
        loaded = [model["name"] for model in body["models"] if model["loaded"]]
        return f"200, engine={engine['selected']}, modelos={loaded}"

    def docs():
        response = client.get("/docs")
        response.raise_for_status()
        return f"200, {len(response.text)} bytes"

    def openapi():
        response = client.get("/openapi.json")
        response.raise_for_status()
        paths = response.json()["paths"]
        if "/v1/analyze" not in paths:
            raise AssertionError("falta /v1/analyze")
        return f"200, {len(paths)} endpoints"

    def analysis():
        response = client.post(
            "/v1/analyze", json={"text": TEXT, "language": "es"}
        )
        response.raise_for_status()
        body = response.json()
        active = [frame["label"] for frame in body["frames"] if frame["isActive"]]
        if not body["sentiment"]["prediction"]:
            raise AssertionError("sin sentimiento")
        return (
            f"200, sentimiento={body['sentiment']['prediction']} "
            f"({body['sentiment']['confidence']}%), encuadres={active[:3]}"
        )

    def dashboard():
        response = client.get("/v1/dashboard/models")
        response.raise_for_status()
        body = response.json()
        if body["engine"] != "bert_pair":
            raise AssertionError(f"dashboard engine={body['engine']}")
        return f"200, sampleSize={body['sampleSize']}, engine={body['engine']}"

    def metrics():
        response = client.get("/metrics")
        response.raise_for_status()
        if "nlp_" not in response.text:
            raise AssertionError("sin métricas nlp_")
        return f"200, {len(response.text)} bytes"

    for name, fn in (
        ("health", health),
        ("docs", docs),
        ("openapi", openapi),
        ("analyze", analysis),
        ("dashboard", dashboard),
        ("metrics", metrics),
    ):
        ok = check(name, fn) and ok

    print("RESULTADO:", "OK" if ok else "FALLÓ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
