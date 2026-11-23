# Despliegue en Azure (API con BETO real)

API pública: **https://20-226-99-99.sslip.io**
Swagger: **https://20-226-99-99.sslip.io/docs**

Motor verificado: `bert_pair` (sentimiento BETO + encuadres BETO, ambos cargados en CPU).
No usa el motor léxico ni el fallback.

## Arquitectura

- **VM**: `vm-migra-api` en `rg-migra-api`, región `brazilsouth`,
  tamaño `Standard_D2as_v4` (2 vCPU, 8 GB RAM), Ubuntu 24.04.
- **Contenedor**: imagen `migra-api` construida con
  `src/cultural_bias/api/Dockerfile.models` (torch CPU).
- **Modelos**: `/opt/migra-models/bert-sentiment` y `/opt/migra-models/bert-frames`,
  montados en el contenedor como `/app/models` (solo lectura).
- **HTTPS**: Caddy como servicio systemd en la VM, certificado automático de
  Let's Encrypt para `20-226-99-99.sslip.io` (resuelve a la IP pública de la VM).
- **Persistencia**: SQLite en `/app/data/api.db` dentro del contenedor.
- **Puertos**: 22, 80 y 443 abiertos en el NSG de Azure.

## Script de instalación

[`src/cultural_bias/deploy/azure_vm_setup.sh`](azure_vm_setup.sh) es idempotente:
instala Docker y Caddy, descarga el ZIP de modelos, clona la rama `integrado`,
construye la imagen, arranca el contenedor y publica HTTPS.

```bash
scp -i ~/.ssh/oracle_migra src/cultural_bias/deploy/azure_vm_setup.sh \
  azureuser@20.226.99.99:/tmp/azure_vm_setup.sh
ssh -i ~/.ssh/oracle_migra azureuser@20.226.99.99 \
  "sudo nohup bash /tmp/azure_vm_setup.sh > /var/log/migra-setup.log 2>&1 &"
```

El ZIP de modelos se sirve desde Blob Storage
(`https://stmigravenez2026.blob.core.windows.net/models/modelos_beto.zip`).
Está en un contenedor público porque solo contiene pesos del modelo.

## Operación

```bash
# Salud y motor
curl https://20-226-99-99.sslip.io/v1/health

# Logs del API
ssh -i ~/.ssh/oracle_migra azureuser@20.226.99.99 "sudo docker logs -f migra-api"

# Logs de Caddy
ssh -i ~/.ssh/oracle_migra azureuser@20.226.99.99 "sudo journalctl -u caddy -f"

# Reiniciar el API
ssh -i ~/.ssh/oracle_migra azureuser@20.226.99.99 "sudo docker restart migra-api"
```

## Costo y cuidado

La cuenta es **Azure for Students** ($100 de crédito). La VM D2as_v4 consume
aproximadamente **$0.10/hora**; el crédito alcanza para varias semanas si se
deja encendida. Si no se necesita 24/7:

```bash
az vm deallocate -g rg-migra-api -n vm-migra-api
az vm start      -g rg-migra-api -n vm-migra-api
```

La IP pública es estática (Standard), así que la URL y el certificado no cambian
al reiniciar.

## Frontend

Configurar la URL base del frontend a `https://20-226-99-99.sslip.io`.
El API tiene CORS abierto (`NLP_CORS_ORIGINS=*`) para la demo.

## Respaldo

El despliegue gratis de Render sigue disponible con motor léxico:
`https://migra-venezuela-api.onrender.com`.
