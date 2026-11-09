# Cómo publicar las ramas en GitHub

Estado: las tres ramas están **commiteadas localmente y verificadas**, pero el
push está bloqueado por permisos de la cuenta de GitHub configurada en esta
máquina.

## Evidencia del bloqueo

```
git push --dry-run origin api
remote: Permission to Diegopp25/corpus_y_entrenamiento_nlp_migra_venezolana.git denied to Jaxtergames234.
fatal: ... The requested URL returned error: 403
```

El git de esta máquina está autenticado como **`Jaxtergames234`**, que no tiene
permiso de escritura en el repositorio de **`Diegopp25`**. No es un problema de
las ramas ni del código.

## Ramas listas

| Rama | Base | Contenido |
|---|---|---|
| `api` | `origin/chore/reorganización-del-repo` | API FastAPI completa: análisis BETO, ingesta, dashboard, monitoreo, tests (88), Docker y docs. |
| `frontend-api` | `origin/dashboard` | Frontend React conectado al API real (sin mocks). |
| `retraining` | `api` | Pipeline de balanceo + validación cruzada y artefactos de reentrenamiento. |

Las tres están en worktrees locales:

- `migra-nlp/` → `api`
- `migra-nlp-frontend/` → `frontend-api`
- `migra-nlp-training/` → `retraining`

## Opción A — autenticarse como la cuenta dueña (recomendada)

```powershell
# 1) Inicia sesión con la cuenta que sí tiene permiso (Diegopp25)
gh auth login

# 2) Desde el checkout principal, publica las tres ramas
cd C:\Users\diego\Documents\deepseek-harness\default-workspace\migra-nlp
git push -u origin api
git push -u origin frontend-api
git push -u origin retraining
```

Si no usas `gh`, configura un Personal Access Token (scope `repo`) de la cuenta
dueña en el Git Credential Manager o en la URL remota temporalmente.

## Opción B — que la cuenta dueña te agregue como colaborador

1. `Diegopp25` → repo → **Settings → Collaborators → Add people** →
   `Jaxtergames234` con permiso **Write**.
2. Aceptar la invitación y repetir los `git push` de la opción A.

## Opción C — entregar un bundle (sin credenciales)

Se generó un bundle con las tres ramas para transferirlas a otra máquina/cuenta:

```powershell
# En la máquina destino, dentro de un clon del repo:
git fetch C:\ruta\a\migra-nlp-ramas.bundle "refs/heads/*:refs/remotes/bundle/*"
git checkout -b api bundle/api
git checkout -b frontend-api bundle/frontend-api
git checkout -b retraining bundle/retraining
```

Luego se hace push normal desde esa cuenta.

## Orden sugerido de PRs

1. `api` → `chore/reorganización-del-repo` (o `main`, según lo que decida el
   equipo; `api` está construida sobre `chore`).
2. `frontend-api` → `dashboard` (contiene el front del amigo + la conexión).
3. `retraining` → `api` (ya incluye el último commit de `api`).

## Verificación antes de subir

```powershell
# API
cd migra-nlp\api
.\.venv\Scripts\python.exe -m pytest tests -q

# Frontend
cd ..\..\migra-nlp-frontend\frontend
npx -y pnpm@10.33.0 run build

# Reentrenamiento (opcional, necesita los pesos de Desktop)
cd ..\..\migra-nlp-training
$env:PYTHONPATH="api"
..\migra-nlp\api\.venv\Scripts\python.exe training\verify_retrained.py --index 0
```
