# 🚀 Local Setup Guide — PR Guardian

Guía paso a paso para levantar PR Guardian en tu máquina local.

---

## Prerrequisitos

| Herramienta | Versión mínima | Para qué |
|-------------|---------------|----------|
| Python | 3.11+ | Backend (webhook, worker, MCP server, agent-core) |
| uv | 0.7+ | Package manager para Python (rápido, lockfile determinístico) |
| Node.js | 20+ | Dashboard (Next.js) |
| Redis | 7+ | Cola de tareas (Celery broker) + Context Cache |
| Git | 2.30+ | Control de versiones |
| ngrok (opcional) | Cualquiera | Exponer webhook local a GitHub |

### Instalar uv (macOS/Linux)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Instalar Redis (macOS)

```bash
brew install redis
brew services start redis

# Verificar que está corriendo
redis-cli ping
# Respuesta esperada: PONG
```

---

## 1. Clonar y preparar el repositorio

```bash
git clone --recursive git@github.com:kubos777/pr-guardian.git
cd pr-guardian

# Cambiar a la rama con el pipeline completo
git checkout ft/async-review-pipeline

# Instalar git hooks (commitlint + husky)
npm install
```

---

## 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus credenciales reales:

```env
# ========================
# GitHub
# ========================
GITHUB_WEBHOOK_SECRET=tu_webhook_secret        # Lo defines tú, luego lo pones en GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxx         # Personal Access Token con permisos: repo, pull_requests
GITHUB_API_URL=https://api.github.com

# ========================
# LLM (Groq + Gemini fallback)
# ========================
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxx            # https://console.groq.com
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxx         # https://aistudio.google.com/apikey
LLM_MODEL=groq/llama-3.3-70b-versatile
LLM_FALLBACK_MODEL=gemini/gemini-2.0-flash
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096

# ========================
# Redis (Celery + Cache)
# ========================
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CONTEXT_CACHE_TTL_SECONDS=300

# ========================
# Database (PostgreSQL)
# ========================
# Docker Compose local: postgresql://pr_guardian:pr_guardian_dev@localhost:5432/pr_guardian
# RDS production: postgresql://pr_guardian:<PASSWORD>@<RDS_ENDPOINT>:5432/pr_guardian
DATABASE_URL=postgresql://pr_guardian:pr_guardian_dev@localhost:5432/pr_guardian

# ========================
# Retry
# ========================
MAX_RETRY_ATTEMPTS=3
RETRY_BACKOFF_BASE_SECONDS=2
RETRY_BACKOFF_MAX_SECONDS=30

# ========================
# Servers
# ========================
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
MCP_SERVER_PORT=8080
DASHBOARD_URL=http://localhost:3000
```

### Cómo obtener cada credencial

| Variable | Dónde obtenerla |
|----------|-----------------|
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens → Fine-grained → Permisos: `Contents: Read`, `Pull requests: Read/Write`, `Issues: Read` |
| `GITHUB_WEBHOOK_SECRET` | Tú lo inventas (string aleatorio). Debe coincidir con lo que configures en GitHub |
| `GROQ_API_KEY` | https://console.groq.com → API Keys (sin tarjeta, gratis) |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey (cuenta Google, gratis) |

---

## 3. Instalar dependencias Python

```bash
# uv crea el virtualenv y resuelve dependencias automáticamente
uv sync
```

Eso es todo. `uv` lee `pyproject.toml`, crea `.venv/`, genera `uv.lock` (determinístico) e instala todo en segundos.

Para activar el entorno manualmente (si necesitas correr scripts directos):

```bash
source .venv/bin/activate
```

O bien, usa `uv run` para ejecutar cualquier comando dentro del virtualenv sin activarlo:

```bash
uv run python -c "import fastapi; print(fastapi.__version__)"
```

---

## 4. Crear el directorio de datos

```bash
mkdir -p data
```

La base de datos SQLite se crea automáticamente al iniciar el webhook handler.

---

## 5. Levantar los servicios

### Opción A: Docker Compose (recomendada — idéntica a producción)

```bash
docker compose up
```

Eso levanta todo: PostgreSQL, Redis, Webhook, Worker y MCP. Para correr en background:

```bash
docker compose up -d

# Ver logs
docker compose logs -f

# Tirar todo
docker compose down
```

Los servicios quedan en:
- **Webhook:** http://localhost:8000
- **MCP:** http://localhost:8080
- **PostgreSQL:** localhost:5432 (user: `pr_guardian`, pass: `pr_guardian_dev`)
- **Redis:** localhost:6379

### Opción B: Sin Docker (servicios nativos)

Necesitas Redis y PostgreSQL corriendo localmente. Usa el script:

```bash
./scripts/dev.sh
```

### Terminal 1: Webhook Handler (FastAPI)

```bash
uv run uvicorn github-integration.webhook_handler:app --host 0.0.0.0 --port 8000 --reload
```

Deberías ver:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2: Celery Worker

```bash
uv run celery -A worker.celery_app worker --loglevel=info --concurrency=2
```

Deberías ver:
```
[config]
  - broker: redis://localhost:6379/0
  - concurrency: 2
[queues]
  - celery (exchange=celery, key=celery)
```

### Terminal 3: MCP Server

```bash
uv run python github-integration/server.py
```

---

## 6. Exponer el webhook a internet (para GitHub)

GitHub necesita enviar webhooks a una URL pública. Usa ngrok:

```bash
# Instalar (si no lo tienes)
brew install ngrok

# Exponer el puerto del webhook
ngrok http 8000
```

ngrok te dará una URL tipo `https://abc123.ngrok-free.app`. Esa es tu webhook URL.

---

## 7. Configurar el webhook en GitHub

1. Ve al repo donde quieres activar PR Guardian
2. **Settings → Webhooks → Add webhook**
3. Configura:
   - **Payload URL:** `https://tu-url-ngrok.ngrok-free.app/webhook`
   - **Content type:** `application/json`
   - **Secret:** El mismo valor que pusiste en `GITHUB_WEBHOOK_SECRET`
   - **Events:** Selecciona "Let me select individual events" → marca solo **Pull requests**
4. Guarda

---

## 8. Probar el flujo completo

1. Crea un PR en el repo configurado
2. Observa los logs en las 3 terminales:
   - **Terminal 1 (Webhook):** Debe loguear el evento recibido y responder `202`
   - **Terminal 2 (Worker):** Debe mostrar las stages ejecutándose: `FETCHING_CONTEXT → ANALYZING → VALIDATING → POSTING_TO_GITHUB → COMPLETED`
   - **Terminal 3 (MCP):** Debe mostrar las llamadas a GitHub API

3. Revisa el PR en GitHub — deberían aparecer comentarios inline del agente

---

## Troubleshooting

| Problema | Solución |
|----------|----------|
| `redis.exceptions.ConnectionError` | Redis no está corriendo. `brew services start redis` |
| `401 Invalid signature` en webhook | El `GITHUB_WEBHOOK_SECRET` no coincide entre `.env` y GitHub |
| Worker no procesa tareas | Verifica que Redis está en `localhost:6379` y Celery conectó al broker |
| `LLMFatalError: Fatal LLM error` | Verifica `GROQ_API_KEY` y `GEMINI_API_KEY` en `.env` |
| `GitHubFatalError: 401` | El `GITHUB_TOKEN` no tiene los permisos necesarios |
| ngrok dice `ERR_NGROK_*` | Crea cuenta gratis en ngrok.com y autentica con `ngrok config add-authtoken` |

---

## Comandos útiles

```bash
# Ver estado de Redis
redis-cli info keyspace

# Ver jobs en la DB
sqlite3 data/pr_guardian.db "SELECT id, status, repo FROM jobs ORDER BY created_at DESC LIMIT 10;"

# Correr tests offline (sin Redis/GitHub/LLM)
uv run pytest -v

# Lint con ruff
uv run ruff check .

# Purgar cola de Celery
uv run celery -A worker.celery_app purge

# Monitorear tareas de Celery en tiempo real
uv run celery -A worker.celery_app events
```

---

## Arquitectura de servicios locales

```
┌─────────────────────────────────────────────────────────┐
│ Tu máquina                                              │
│                                                         │
│  :8000 Webhook Handler (FastAPI/Uvicorn)                │
│    ↓ encola job                                         │
│  Redis (:6379)                                          │
│    ↓ consume                                            │
│  Celery Worker                                          │
│    ↓ llama tools                                        │
│  :8080 MCP Server (FastMCP)                             │
│    ↓ GitHub API                                         │
│  ────────────── internet ──────────────                 │
│  GitHub API + Groq/Gemini API                        │
└─────────────────────────────────────────────────────────┘
```

---

## Dashboard (opcional por ahora)

```bash
cd dashboard
npm install
npm run dev
# → http://localhost:3000
```

> ⚠️ El dashboard aún no está conectado al backend. Es placeholder para la demo.
