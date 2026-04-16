# QA Chat Tester

Plataforma SaaS interna para QA automatizado de agentes de IA conversacionales. Simula usuarios reales con [Google ADK](https://google.github.io/adk-docs/) + Gemini, registra cada intercambio en MongoDB, genera análisis automático con IA y expone un dashboard multi-tenant para explorar resultados.

## Tabla de contenidos

- [Arquitectura](#arquitectura)
- [Stack](#stack)
- [Inicio rápido con Docker](#inicio-rápido-con-docker)
- [Instalación local](#instalación-local)
- [Variables de entorno](#variables-de-entorno)
- [Servicios](#servicios)
  - [API (FastAPI)](#api-fastapi)
  - [Worker (Celery)](#worker-celery)
  - [Escalado para alta carga (500+ conv/h)](#escalado-para-alta-carga-500-conversacioneshora)
  - [Dashboard](#dashboard)
  - [CLI](#cli)
- [Multi-tenancy](#multi-tenancy)
- [Test Suites y casos](#test-suites-y-casos)
- [Ejecuciones (Runs)](#ejecuciones-runs)
- [Formato del payload de un caso](#formato-del-payload-de-un-caso)
- [API del agente bajo prueba](#api-del-agente-bajo-prueba)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Variables de entorno — referencia completa](#variables-de-entorno--referencia-completa)

---

## Arquitectura

```
┌─────────────┐    REST/WS    ┌──────────────────┐
│  Dashboard  │◄─────────────►│   API (FastAPI)  │
│  (Vue 3)    │               │   /v1/*          │
└─────────────┘               └────────┬─────────┘
                                       │
                         ┌─────────────┼─────────────┐
                         │             │             │
                    ┌────▼───┐   ┌─────▼──┐   ┌─────▼───┐
                    │MongoDB │   │  MySQL │   │  Redis  │
                    │(datos) │   │(users) │   │(broker) │
                    └────────┘   └────────┘   └────┬────┘
                                                    │
                                           ┌────────▼────────┐
                                           │  Worker (Celery) │
                                           │  run_suite / run_case │
                                           └────────┬────────┘
                                                    │
                                           ┌────────▼────────┐
                                           │  CLI (main.py)  │
                                           │  UserAgent +    │
                                           │  AnalysisAgent  │
                                           └─────────────────┘
```

### Flujo de una ejecución

```
POST /v1/runs/suite/{id}
  │
  ├─ Crea documento en runs (status: pending)
  └─ Celery task: run_suite.delay(...)
       │
       ├─ Para cada test_case:
       │   ├─ UserAgent simula al usuario → POST /chat al agente externo
       │   │   └─ Guarda cada turno en MongoDB (logs)
       │   └─ AnalysisAgent evalúa la conversación → guarda en MongoDB (insights)
       │
       └─ Actualiza runs (status: completed / stopped / failed)
```

---

## Stack

| Capa | Tecnología |
|------|-----------|
| API | FastAPI + Uvicorn |
| Agentes IA | Google ADK (Gemini 2.5 Flash) |
| Base de datos operacional | MongoDB 7 |
| Autenticación admins | MySQL 8 + SQLAlchemy |
| Cola de tareas | Celery 5 + Redis 7 |
| Dashboard | Vue 3 + Tailwind CSS (SPA, sin build step) |
| Dependencias | uv + pyproject.toml |

---

## Inicio rápido con Docker

### 1. Clonar y configurar

```bash
git clone <repo-url>
cd qaChatTester
cp .env.example .env   # editar con tus credenciales
```

### 2. Levantar todos los servicios

```bash
docker compose up -d
```

Servicios disponibles:

| Servicio | URL |
|---------|-----|
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Dashboard | http://localhost:8765 |
| MongoDB | localhost:27017 |
| MySQL | localhost:3306 |
| Redis | localhost:6379 |

### 3. Ejecutar casos desde CLI (una vez)

```bash
# Con archivo JSON de casos
docker compose run --rm cli json_file=cases.json batch_size=10

# Caso único
docker compose run --rm cli context="El usuario quiere cancelar su suscripción" user_id=123
```

### 4. Construir imágenes individualmente

```bash
docker build -f Dockerfile.api       -t qa-api       .
docker build -f Dockerfile.worker    -t qa-worker     .
docker build -f Dockerfile.dashboard -t qa-dashboard  .
docker build -f Dockerfile.cli       -t qa-cli        .
```

---

## Instalación local

```bash
# Python 3.13 requerido
uv sync

# Servicios externos requeridos
# - MongoDB (mongodb://localhost:27017)
# - MySQL   (localhost:3306)
# - Redis   (localhost:6379)

# Copiar y editar .env
cp .env.example .env
```

Levantar cada servicio en terminales separadas:

```bash
# 1. API
uv run uvicorn server.main:app --reload --port 8000

# 2. Worker
uv run celery -A celery_queue.config:celery_app worker --loglevel=info

# 3. Dashboard
python dashboard/server.py

# 4. CLI (opcional, ejecución directa)
uv run python main.py json_file=cases.json batch_size=10
```

---

## Variables de entorno

Crea `.env` en la raíz (o usa variables de entorno del sistema):

```env
# ── Agente bajo prueba (requeridas) ──────────────────────────────────────────
GOOGLE_API_KEY=AIzaSy...
GOOGLE_GENAI_USE_VERTEXAI=False
AGENT_URL=https://tu-agente.run.app
AGENT_TOKEN=eyJhbG...

# ── Modelos ───────────────────────────────────────────────────────────────────
MODEL_NAME=gemini-2.5-flash

# ── MongoDB (datos operacionales) ─────────────────────────────────────────────
MONGO_URI=mongodb://root:root@localhost:27017/?authSource=admin&tls=false
MONGO_DB=qa_chat_tester

# ── MySQL (autenticación de admins) ──────────────────────────────────────────
DATABASE_URL=mysql+pymysql://root:root@localhost/qa_chat_tester
# Alternativa: SQLite automático si no se define DATABASE_URL
# DATABASE_URL=sqlite:///users.db

# ── Redis (broker Celery) ────────────────────────────────────────────────────
REDIS_URI=redis://localhost:6379

# ── Multi-tenancy ─────────────────────────────────────────────────────────────
DEFAULT_ACCOUNT_ID=3057

# ── Dashboard ────────────────────────────────────────────────────────────────
# URL de la API inyectada en el dashboard (variable de entorno del servidor dashboard)
API_BASE_URL=http://localhost:8000/v1

# ── Seguridad ────────────────────────────────────────────────────────────────
PASSWORD_SALT=cambia_esto_antes_de_produccion
CORS_ORIGINS=http://localhost:3000,http://localhost:8765

# ── Comportamiento del agente ────────────────────────────────────────────────
MAX_CHAT_ITERATIONS=20
ITERATION_TIMEOUT=120
ANALYSIS_TIMEOUT=120
RUN_TIMEOUT=600
MAX_ANALYSIS_RETRIES=3
MAX_CONV_RETRIES=3
MAX_CONCURRENT_AGENTS=3
REQUEST_TIMEOUT=120

# ── Celery worker ────────────────────────────────────────────────────────────
WORKER_CONCURRENCY=1
```

---

## Servicios

### API (FastAPI)

Corre en el puerto **8000**. Toda la lógica de datos se expone como REST bajo `/v1/`.

#### Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/v1/stats` | Conteos globales del tenant |
| `GET` | `/v1/accounts` | Lista todas las cuentas (tenants) |
| `POST` | `/v1/accounts` | Crear nueva cuenta |
| `GET` | `/v1/conversations` | Lista paginada de conversaciones (con filtros) |
| `GET` | `/v1/conversations/{session_id}` | Detalle: mensajes + insight + caso |
| `PATCH` | `/v1/conversations/{session_id}/insight` | Actualizar/crear insight manualmente |
| `POST` | `/v1/conversations/{session_id}/analyse` | Disparar análisis IA en background |
| `GET` | `/v1/analyses` | Lista paginada de análisis (con filtros) |
| `GET` | `/v1/suites` | Lista paginada de test suites |
| `POST` | `/v1/suites` | Crear suite |
| `PATCH` | `/v1/suites/{id}` | Editar suite |
| `DELETE` | `/v1/suites/{id}` | Eliminar suite y sus casos |
| `GET` | `/v1/suites/{id}/cases` | Lista paginada de casos del suite |
| `POST` | `/v1/suites/{id}/cases` | Crear caso |
| `POST` | `/v1/suites/{id}/cases/upload` | Subir JSON masivo de casos |
| `PATCH` | `/v1/cases/{id}` | Editar caso |
| `DELETE` | `/v1/cases/{id}` | Eliminar caso |
| `GET` | `/v1/runs` | Lista paginada de ejecuciones |
| `POST` | `/v1/runs/suite/{suite_id}` | Ejecutar suite (o selección de casos) |
| `POST` | `/v1/runs/case/{case_id}` | Ejecutar un caso individual |
| `POST` | `/v1/runs/{run_id}/pause` | Pausar ejecución en curso |
| `POST` | `/v1/runs/{run_id}/resume` | Reanudar ejecución pausada |
| `POST` | `/v1/runs/{run_id}/stop` | Detener ejecución |
| `GET` | `/v1/export/conversations` | Descargar `.xlsx` con todas las conversaciones |

**Todos los endpoints de datos requieren el header `X-Account-ID: <tenant_id>`.**

#### Paginación

Todos los endpoints de listado soportan:
- `?page=1` — número de página (default: 1)
- `?page_size=20` — ítems por página (default varía por endpoint, máx: 200)

Respuesta paginada:
```json
{
  "items": [...],
  "total": 347,
  "page": 2,
  "page_size": 20,
  "pages": 18
}
```

#### Filtros de conversaciones

```
GET /v1/conversations?status=done&objective=ok&run_filter=<run_id>&search_field=user_id&search_query=123
```

| Param | Valores | Descripción |
|-------|---------|-------------|
| `status` | `all` / `done` / `pend` | Tiene análisis o no |
| `objective` | `all` / `ok` / `fail` | Objetivo cumplido |
| `run_filter` | UUID | Solo conversaciones de ese run |
| `search_field` | `session_id` / `run_id` / `user_id` / `scenario` / `scenario_group_id` | Campo a buscar |
| `search_query` | string | Texto a buscar (regex, case-insensitive) |

#### Filtros de análisis

```
GET /v1/analyses?status=fail&group=TC005B&search=paquetes
```

| Param | Valores | Descripción |
|-------|---------|-------------|
| `status` | `all` / `ok` / `fail` / `pending` | Estado del análisis |
| `group` | string | Filtrar por `scenario_group_id` |
| `search` | string | Buscar en el texto del análisis |

---

### Worker (Celery)

Procesa las tareas de ejecución de casos en background usando arquitectura paralela: cada caso se despacha como un task independiente, permitiendo ejecución masiva concurrente.

```bash
# Local — desarrollo (1 caso a la vez)
uv run celery -A celery_queue.config:celery_app worker --loglevel=info

# Local — alta concurrencia
WORKER_CONCURRENCY=15 uv run celery -A celery_queue.config:celery_app worker --loglevel=info
```

**Tareas disponibles:**

| Task | Descripción |
|------|-------------|
| `jobs.run_suite` | Orquestador: despacha N tasks `process_case` en paralelo vía `celery.group` |
| `jobs.run_case` | Ejecuta un caso individual |
| `jobs.process_case` | Ejecuta **una** conversación completa (unidad mínima de ejecución) |

**Comportamiento de pause/stop con ejecución paralela:**

Cada `process_case` consulta el estado del run en MongoDB antes de iniciar la conversación. Si el run está pausado espera; si está detenido sale sin procesar. Las conversaciones ya en curso no se interrumpen a mitad — terminan y la siguiente no arranca.

---

### Escalado para alta carga (500+ conversaciones/hora)

#### Arquitectura paralela

```
Antes (serie):   run_suite → [caso1 → caso2 → caso3 → ...]   1 proceso
Después (paralelo): run_suite ─► process_case(caso1)  ┐
                                 process_case(caso2)  ├─ N workers × C slots
                                 process_case(caso3)  │
                                 ...proceso500        ┘
```

#### Fórmula de capacidad

```
conversaciones/hora = réplicas_worker × WORKER_CONCURRENCY × (3600 / duración_promedio_segundos)
```

**Ejemplo con conversaciones de 5 min (300 s):**

| Réplicas | Concurrencia | Slots totales | Conv/hora |
|----------|-------------|---------------|-----------|
| 1        | 10          | 10            | 120       |
| 2        | 15          | 30            | 360       |
| 3        | 15          | 45            | 540 ✓     |
| 3        | 20          | 60            | 720       |
| 5        | 20          | 100           | 1 200     |

> **Regla práctica**: para 500 conv/h con duración promedio de 5 min necesitas **~42 slots concurrentes** activos. Con `3 réplicas × 15 concurrencia = 45 slots` lo alcanzas con margen.

#### Escalado con Docker Compose

```bash
# Escalar a 3 réplicas, 15 slots cada una → 540 conv/h
WORKER_CONCURRENCY=15 docker compose up -d --scale worker=3

# Verificar workers activos
docker compose ps worker

# Monitoreo en tiempo real con Flower
docker compose --profile monitoring up -d flower
# → http://localhost:5555
```

#### Escalado local (sin Docker)

```bash
# Terminal 1 — worker A
WORKER_CONCURRENCY=15 uv run celery -A celery_queue.config:celery_app worker \
  --loglevel=info --hostname=worker-a@%h

# Terminal 2 — worker B
WORKER_CONCURRENCY=15 uv run celery -A celery_queue.config:celery_app worker \
  --loglevel=info --hostname=worker-b@%h

# Terminal 3 — worker C
WORKER_CONCURRENCY=15 uv run celery -A celery_queue.config:celery_app worker \
  --loglevel=info --hostname=worker-c@%h
```

#### Recursos de infraestructura

Cada slot Celery (prefork) es un proceso Python independiente:

| Recurso | Por slot | 45 slots (3×15) |
|---------|----------|-----------------|
| RAM     | ~200 MB  | ~9 GB           |
| CPU     | I/O-bound (espera LLM) | 4-8 cores suficientes |

**Recomendaciones de máquina para 3 réplicas × 15 concurrencia:**
- RAM: 16 GB mínimo (9 GB workers + SO + Mongo + Redis)
- CPU: 4-8 vCPUs (el trabajo es mayormente I/O, no CPU)
- Red: 100 Mbps+ (cada conversación hace múltiples llamadas HTTP a Gemini y al agente)

#### Rate limits de Gemini

El limitante externo más común. Si aparecen errores `429 Resource Exhausted`:

```
Error: 429 Resource Exhausted / quota exceeded
```

El worker reintenta automáticamente con backoff (60 s entre intentos, máx 3 reintentos). Para evitar alcanzar el límite:

| Tier Gemini | RPM aproximado | Slots recomendados |
|-------------|---------------|-------------------|
| Free        | 15 RPM        | 2-3               |
| Pay-as-you-go | 1 000 RPM   | 20-50             |
| Enterprise  | 10 000+ RPM   | 100+              |

```bash
# Reducir concurrencia si hay errores 429 persistentes
WORKER_CONCURRENCY=8 docker compose up -d --scale worker=3
```

---

### Dashboard

Interfaz web Vue 3 + Tailwind que consume la API. Corre en el puerto **8765**.

```bash
# Local
python dashboard/server.py

# Puerto personalizado
python dashboard/server.py port=9000
```

La URL de la API se inyecta automáticamente desde la variable de entorno `API_BASE_URL` (default: `http://localhost:8000/v1`). No hay input manual en la UI.

#### Secciones

| Sección | Descripción |
|---------|-------------|
| **Dashboard** | Stats globales + lista de conversaciones recientes. Auto-refresh 5s. |
| **Conversaciones** | Lista paginada con filtros (estado, objetivo, run, búsqueda). Timeline completo de cada conversación. Click en el número de turno → raw response JSON. Chips de metadata copiables al portapapeles. Marcar como cumplida/fallida manualmente. Generar análisis con IA. |
| **Análisis** | Lista paginada de insights con estadísticas, gráficas (distribución + por grupo) y reporte ejecutivo descargable. |
| **Test Suites** | CRUD de suites y casos. Subir JSON masivo. Selección múltiple para ejecutar N casos específicos. Expansión inline de payload. |
| **Ejecuciones** | Historial de runs con progreso, estado y controles de pausa/reanudación/detención. |

#### Selector de tenant

En la barra lateral aparece un selector de cuenta (`X-Account-ID`). Los datos disponibles son los registrados en la colección `accounts` de MongoDB. El tenant se puede crear desde el mismo selector.

---

### CLI

Modo de ejecución directa sin pasar por la cola de Celery. Útil para desarrollo o pruebas puntuales.

```bash
# Caso único
uv run python main.py context="El usuario quiere cancelar" user_id=12345

# Batch desde archivo
uv run python main.py json_file=cases.json batch_size=5

# Con modelo específico
uv run python main.py json_file=cases.json model=gemini-2.0-flash
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `context` | `"No context provided."` | Contexto/escenario del caso |
| `user_id` | `"default_user"` | ID del usuario simulado |
| `model` | `$MODEL_NAME` | Modelo Gemini a usar |
| `json_file` | — | Ruta a JSON con lista de casos |
| `batch_size` | `10` | Conversaciones concurrentes (con `json_file`) |

---

## Multi-tenancy

Cada recurso en MongoDB (logs, insights, cases, suites, runs, conversations) tiene un campo `account_id` que identifica el tenant. Todos los endpoints de la API requieren el header `X-Account-ID`.

La colección `accounts` en MongoDB almacena los tenants conocidos:

```json
{
  "account_id": "3057",
  "name": "Acme Corp",
  "description": "Entorno de producción",
  "created_at": "...",
  "updated_at": "..."
}
```

Los usuarios (administradores) se almacenan en MySQL y están asociados a un `account_id`. Todos los usuarios tienen permisos de admin — no hay restricciones por rol.

---

## Test Suites y casos

Un **Suite** es un contenedor de casos de prueba. Un **Caso** tiene título, descripción y un payload JSON que se pasa como contexto al agente simulado.

### Crear suite y casos vía API

```bash
# Crear suite
curl -X POST http://localhost:8000/v1/suites \
  -H "X-Account-ID: 3057" \
  -H "Content-Type: application/json" \
  -d '{"title": "Paquetes Escolares Q1", "description": "Flujos de confirmación"}'

# Subir casos masivamente desde JSON
curl -X POST http://localhost:8000/v1/suites/{suite_id}/cases/upload?replace=true \
  -H "X-Account-ID: 3057" \
  -F "file=@cases.json"
```

---

## Ejecuciones (Runs)

### Disparar una ejecución

```bash
# Ejecutar todo el suite
curl -X POST http://localhost:8000/v1/runs/suite/{suite_id} \
  -H "X-Account-ID: 3057" \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini-2.5-flash"}'

# Ejecutar solo casos seleccionados
curl -X POST http://localhost:8000/v1/runs/suite/{suite_id} \
  -H "X-Account-ID: 3057" \
  -H "Content-Type: application/json" \
  -d '{"case_ids": ["<id1>", "<id2>"]}'
```

### Estados de un Run

| Estado | Descripción |
|--------|-------------|
| `pending` | En cola, esperando al worker |
| `running` | En ejecución |
| `paused` | Pausado por el usuario (continuará después del caso actual) |
| `stopped` | Detenido por el usuario |
| `completed` | Todos los casos procesados |
| `failed` | Error inesperado en el task |

### Controles

```bash
curl -X POST http://localhost:8000/v1/runs/{run_id}/pause   -H "X-Account-ID: 3057"
curl -X POST http://localhost:8000/v1/runs/{run_id}/resume  -H "X-Account-ID: 3057"
curl -X POST http://localhost:8000/v1/runs/{run_id}/stop    -H "X-Account-ID: 3057"
```

---

## Formato del payload de un caso

Cada caso puede tener cualquier estructura JSON. Los campos más usados por los agentes:

```json
{
  "user_id": "58421687",
  "prompt": "JOSÉ ANTONIO AVELAR SANDOVAL de 76045 contacta al chatbot para confirmar...",
  "analysisPrompt": "El bot debe confirmar el ticket y dar número de seguimiento.",
  "scenario": "Ticket – Paquetes Escolares | Director | B. Tickets SDP",
  "ScenarioGroupId": "TC005B",
  "campaigns": [
    {
      "campaign_id": "cmp-456",
      "campaign_name": "Confirmación Paquetes Escolares Q1",
      "whatsapp_template_name": "confirmacion_de_solicitud_de_paquetes_escolares_q1"
    }
  ]
}
```

| Campo | Descripción |
|-------|-------------|
| `user_id` | ID del usuario simulado (requerido) |
| `prompt` | Instrucciones narrativas para el `UserAgent` |
| `analysisPrompt` | Criterio de éxito para el `AnalysisAgent` |
| `scenario` | Nombre descriptivo del escenario |
| `ScenarioGroupId` | Agrupación de escenarios (ej. `TC005B`) |
| `campaigns` | Campañas WhatsApp activas durante el escenario |

El objeto completo se pasa como `context` al `UserAgent` y al `AnalysisAgent`.

---

## API del agente bajo prueba

El agente externo debe exponer un endpoint `POST /chat`:

**Request:**
```json
{
  "account_id": "3057",
  "user_id": "12345",
  "text": "Hola, necesito ayuda con mi paquete escolar",
  "images": [],
  "attachments": [],
  "session_id": "abc123",
  "session_backend": "redis",
  "persist_session": true,
  "campaigns": [],
  "bot_message": { "text": "", "is_hsm": false, "hsm_name": "" }
}
```

**Headers:**
```
Authorization: Bearer <AGENT_TOKEN>
Content-Type: application/json
```

**Response mínima esperada:**
```json
{
  "session_id": "abc123",
  "text": "Hola, ¿en qué puedo ayudarte?"
}
```

El campo `session_id` es obligatorio en la respuesta. El campo `text` es el que se muestra en el dashboard como respuesta del bot.

---

## Estructura del proyecto

```
qaChatTester/
│
├── main.py                    # CLI: orquesta UserAgent + AnalysisAgent
├── batch_runner.py            # Lanzador paralelo (subprocesos main.py)
├── pyproject.toml
├── uv.lock
│
├── Dockerfile.api             # Imagen: FastAPI
├── Dockerfile.worker          # Imagen: Celery worker
├── Dockerfile.dashboard       # Imagen: Dashboard HTTP server
├── Dockerfile.cli             # Imagen: CLI de ejecución
├── docker-compose.yml         # Orquestación completa
│
├── server/                    # FastAPI application
│   ├── main.py                # App, lifespan, middlewares
│   └── api/v1/
│       ├── accounts.py        # CRUD de tenants
│       ├── analyses.py        # Listado paginado de insights
│       ├── cases.py           # CRUD de casos individuales
│       ├── conversations.py   # Listado, detalle, análisis manual
│       ├── deps.py            # Dependency: get_account_id
│       ├── export.py          # Descarga XLSX
│       ├── pagination.py      # Helper make_page()
│       ├── runs.py            # Ejecuciones + controles
│       ├── stats.py           # Conteos globales
│       ├── suites.py          # CRUD de suites + casos
│       └── xlsx.py            # Builder .xlsx sin dependencias
│
├── celery_queue/              # Cola de tareas
│   ├── config.py              # Instancia Celery + configuración
│   ├── worker.py              # Entry point del worker
│   └── jobs/
│       └── tasks.py           # run_suite, run_case
│
├── agents/                    # Agentes Google ADK
│   ├── agent_base.py          # Clase base: model, tools, _build_tool()
│   ├── user.py                # UserAgent — simula al usuario
│   └── analysis.py            # AnalysisAgent + AnalysisAgentManual
│
├── tools/                     # Herramientas de los agentes
│   ├── common.py              # send_to_agent, save_interaction, save_analysis
│   └── messages.py            # get_messages_by_session_id
│
├── lib/                       # Conexiones a servicios
│   ├── mongo.py               # MongoDB singleton
│   ├── sql_db.py              # SQLAlchemy (MySQL o SQLite)
│   ├── mysql.py               # Alias → sql_db (deprecated)
│   └── cache.py               # Redis singleton
│
├── db/                        # Capa de datos
│   ├── log.py                 # LogDB: singleton db for logging (→ MongoDB)
│   ├── models/
│   │   └── user.py            # SQLAlchemy model: User
│   ├── repositories/
│   │   ├── base.py            # BaseMongoRepository
│   │   ├── account_repository.py
│   │   ├── case_repository.py
│   │   ├── conversation_repository.py
│   │   ├── insight_repository.py
│   │   ├── log_repository.py
│   │   ├── run_repository.py
│   │   ├── test_case_repository.py
│   │   ├── test_suite_repository.py
│   │   └── user_repository.py
│   └── migrations/
│       └── 001_initial.sql    # Schema MySQL (referencia; SQLAlchemy lo crea auto)
│
├── utils/
│   ├── agent_runner.py        # Wrapper sobre Google ADK Runner
│   ├── prompt_utils.py        # extract_json_blocks
│   ├── tool_utils.py          # to_snake_case
│   └── built_in_func.py       # Auxiliares internos
│
└── dashboard/
    ├── server.py              # HTTP server stdlib: sirve index.html + inyecta API_BASE_URL
    └── index.html             # SPA: Vue 3 + Tailwind + Chart.js
```

---

## Variables de entorno — referencia completa

| Variable | Requerida | Default | Descripción |
|----------|-----------|---------|-------------|
| `GOOGLE_API_KEY` | Sí | — | API key de Google AI Studio |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `False` | Usar Vertex AI en lugar de AI Studio |
| `AGENT_URL` | Sí | — | URL base del agente bajo prueba |
| `AGENT_TOKEN` | Sí | — | Bearer token del agente |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Modelo Gemini para los agentes QA |
| `MONGO_URI` | Sí | — | URI de conexión a MongoDB |
| `MONGO_DB` | No | `qa_chat_tester` | Nombre de la base de datos en MongoDB |
| `DATABASE_URL` | No | `sqlite:///users.db` | URL SQLAlchemy para MySQL (o SQLite) |
| `REDIS_URI` | No | `redis://localhost:6379` | URI de Redis (broker Celery) |
| `DEFAULT_ACCOUNT_ID` | No | `default` | Tenant por defecto cuando no se pasa `account_id` |
| `API_BASE_URL` | No | `http://localhost:8000/v1` | URL de la API inyectada en el dashboard |
| `PASSWORD_SALT` | No | `qa_chat_tester_salt_v1` | Salt para hash SHA-256 de contraseñas |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Orígenes CORS permitidos (coma-separados) |
| `PORT` | No | `8000` | Puerto de la API |
| `WORKER_CONCURRENCY` | No | `1` | Workers concurrentes en Celery |
| `MAX_CHAT_ITERATIONS` | No | `20` | Máximo de turnos por conversación |
| `ITERATION_TIMEOUT` | No | `120` | Timeout por llamada al LLM (segundos) |
| `ANALYSIS_TIMEOUT` | No | `120` | Timeout por intento de análisis (segundos) |
| `RUN_TIMEOUT` | No | `600` | Timeout total por sesión (segundos) |
| `MAX_ANALYSIS_RETRIES` | No | `3` | Reintentos del AnalysisAgent |
| `MAX_CONV_RETRIES` | No | `3` | Reintentos de conversación si no genera mensajes |
| `MAX_CONCURRENT_AGENTS` | No | `3` | Agentes concurrentes dentro de un proceso |
| `REQUEST_TIMEOUT` | No | `120` | Timeout HTTP hacia el agente externo (segundos) |
