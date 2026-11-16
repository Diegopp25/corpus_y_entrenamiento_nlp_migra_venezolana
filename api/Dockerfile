# =============================================================================
# Imagen del API de cobertura mediática de la migración venezolana
# -----------------------------------------------------------------------------
# Construcción (el contexto es la carpeta api/):
#
#   docker build -t migra-nlp-api .
#
# Con soporte de modelos BETO (torch + transformers, imagen mucho más pesada):
#
#   docker build --build-arg INSTALL_MODELS=1 -t migra-nlp-api:models .
#
# Los pesos NO se copian en la imagen: se montan como volumen (ver docker-compose.yml).
# =============================================================================

ARG PYTHON_VERSION=3.12

# ------------------------------ etapa builder --------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ARG INSTALL_MODELS=0

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Se copian ambos archivos porque requirements-models.txt hace `-r requirements.txt`.
COPY requirements.txt requirements-models.txt ./

# Entorno virtual aislado que luego se copia a la imagen final.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && if [ "$INSTALL_MODELS" = "1" ]; then \
         /opt/venv/bin/pip install -r requirements-models.txt; \
       else \
         /opt/venv/bin/pip install -r requirements.txt; \
       fi

# ------------------------------ etapa runtime --------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    NLP_ENVIRONMENT=prod \
    NLP_DATABASE_PATH=/app/data/api.db \
    NLP_ARTIFACTS_DIR=/app/artifacts \
    NLP_CORPUS_CSV_PATH=/app/corpus/dataset_migracion_venezolana_labeled.csv

# Usuario sin privilegios (la imagen slim ya trae `useradd`).
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app

# Carpetas de escritura (SQLite, artefactos, pesos montados).
RUN mkdir -p /app/data /app/artifacts /app/models \
    && chown -R app:app /app

USER app

EXPOSE 8000

# `curl` no existe en python:*-slim: se usa la stdlib para el healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
