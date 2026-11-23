#!/usr/bin/env bash
# Instala y arranca la API con BETO real en la VM Ubuntu de Azure.
# Ejecutar como root: sudo bash azure_vm_setup.sh
set -euo pipefail

MODELS_URL="${MODELS_URL:-https://stmigravenez2026.blob.core.windows.net/models/modelos_beto.zip}"
DOMAIN="${DOMAIN:-20-226-99-99.sslip.io}"
REPO_URL="${REPO_URL:-https://github.com/Diegopp25/corpus_y_entrenamiento_nlp_migra_venezolana.git}"
BRANCH="${BRANCH:-integrado}"
APP_DIR="/opt/migra"
MODELS_DIR="/opt/migra-models"

log() { echo "[azure-setup] $*"; }

export DEBIAN_FRONTEND=noninteractive
log "Instalando paquetes base"
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl git unzip docker.io

systemctl enable --now docker

log "Descargando modelos BETO desde Blob"
mkdir -p "$MODELS_DIR"
curl -fL "$MODELS_URL" -o /opt/modelos_beto.zip
unzip -q -o /opt/modelos_beto.zip -d "$MODELS_DIR"
rm -f /opt/modelos_beto.zip
test -f "$MODELS_DIR/bert-sentiment/model.safetensors"
test -f "$MODELS_DIR/bert-frames/model.safetensors"
log "Modelos listos en $MODELS_DIR"

log "Clonando repositorio"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$APP_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
else
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$APP_DIR"
fi

log "Construyendo imagen (torch + transformers; puede tardar)"
docker build -f "$APP_DIR/src/cultural_bias/api/Dockerfile.models" -t migra-api "$APP_DIR/src/cultural_bias/api"

log "Arrancando contenedor"
docker rm -f migra-api >/dev/null 2>&1 || true
docker run -d --name migra-api --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -e NLP_ENVIRONMENT=prod \
  -e NLP_ENGINE=bert_pair \
  -e NLP_DEVICE=cpu \
  -e NLP_MODELS_DIR=/app/models \
  -e NLP_SENTIMENT_MODEL_DIR=/app/models/bert-sentiment \
  -e NLP_FRAMES_MODEL_DIR=/app/models/bert-frames \
  -e NLP_DATABASE_PATH=/app/data/api.db \
  -e NLP_CORS_ORIGINS='*' \
  -v "$MODELS_DIR:/app/models:ro" \
  migra-api

log "Instalando Caddy (HTTPS automático)"
if ! command -v caddy >/dev/null 2>&1; then
  curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=amd64" -o /usr/local/bin/caddy
  chmod +x /usr/local/bin/caddy
fi
mkdir -p /etc/caddy
cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
EOF
cat > /etc/systemd/system/caddy.service <<'EOF'
[Unit]
Description=Caddy
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
Restart=always
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now caddy
systemctl restart caddy

log "Esperando API..."
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/v1/health >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
curl -fsS http://127.0.0.1:8000/v1/health || true
echo
log "LISTO: https://$DOMAIN/docs"
