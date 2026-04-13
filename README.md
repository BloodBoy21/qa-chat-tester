# QA Chat Tester

Herramienta de QA automatizado para probar agentes de IA conversacionales. Simula usuarios reales usando [Google ADK](https://google.github.io/adk-docs/) con modelos Gemini, registra cada intercambio en SQLite y genera un análisis automático de cada sesión.

## Tabla de contenidos

- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Variables de entorno](#variables-de-entorno)
- [Uso](#uso)
  - [Ejecución simple](#ejecución-simple)
  - [Batch paralelo — batch\_runner.py](#batch-paralelo--batch_runnerpy)
  - [Formato de cases.json](#formato-de-casesjson)
- [Dashboard](#dashboard)
- [Base de datos](#base-de-datos)
- [Estructura del proyecto](#estructura-del-proyecto)
- [API del agente bajo prueba](#api-del-agente-bajo-prueba)
- [Variables de entorno avanzadas](#variables-de-entorno-avanzadas)

---

## Arquitectura

```
batch_runner.py          → Divide cases.json en sub-batches y lanza subprocesos
    └── main.py          → Procesa un batch; orquesta los agentes ADK
         ├── UserAgent       → Simula al usuario: redacta y envía mensajes via HTTP
         └── AnalysisAgent   → Analiza la conversación completa y guarda insights
              └── AnalysisAgentManual  → Fallback sin tools cuando ADK falla
```

### Flujo por sesión

```
batch_runner.py
  │  Divide cases.json → archivos temporales por batch
  │  Lanza N subprocesos Python (main.py) en paralelo
  │
main.py (por cada caso)
  │
  ├─ UserAgent recibe el contexto del caso
  │   └─ Llama send_to_agent() → POST /chat → guarda en logs.db
  │   └─ Itera hasta que la conversación termina o alcanza MAX_CHAT_ITERATIONS
  │
  └─ AnalysisAgent recibe el session_id
      └─ Llama get_messages_by_session_id() → lee logs.db
      └─ Genera análisis y llama save_analysis() → guarda en insights
```

---

## Requisitos

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (recomendado)

---

## Instalación

```bash
# Clonar y entrar al proyecto
git clone <repo-url>
cd qaChatTester

# Instalar dependencias con uv
uv sync

# O con pip
pip install -e .
```

Crea un archivo `.env` en la raíz (ver [Variables de entorno](#variables-de-entorno)).

---

## Variables de entorno

Crea `.env` en la raíz del proyecto:

```env
# Requeridas
GOOGLE_API_KEY=AIzaSy...
AGENT_URL=https://mi-agente.run.app
AGENT_TOKEN=eyJhbG...

# Opcionales
MODEL_NAME=gemini-2.5-flash
APP_NAME=qa-tester
GOOGLE_GENAI_USE_VERTEXAI=False
MAX_CHAT_ITERATIONS=20
ITERATION_TIMEOUT=120
ANALYSIS_TIMEOUT=120
RUN_TIMEOUT=600
MAX_ANALYSIS_RETRIES=3
REQUEST_TIMEOUT=120
```

| Variable | Requerida | Default | Descripción |
|---|---|---|---|
| `GOOGLE_API_KEY` | Sí | — | API key de Google AI Studio |
| `AGENT_URL` | Sí | — | URL base del agente bajo prueba |
| `AGENT_TOKEN` | Sí | — | Bearer token para autenticarse con el agente |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Modelo Gemini para los agentes QA |
| `APP_NAME` | No | `default_app_name` | Nombre de la app en ADK |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `False` | Usar Vertex AI en lugar de AI Studio |
| `MAX_CHAT_ITERATIONS` | No | `20` | Máximo de turnos por conversación |
| `ITERATION_TIMEOUT` | No | `120` | Timeout por llamada al LLM (segundos) |
| `ANALYSIS_TIMEOUT` | No | `120` | Timeout por intento de análisis (segundos) |
| `RUN_TIMEOUT` | No | `600` | Timeout total por sesión completa (segundos) |
| `MAX_ANALYSIS_RETRIES` | No | `3` | Reintentos del AnalysisAgent antes del fallback manual |
| `REQUEST_TIMEOUT` | No | `120` | Timeout HTTP hacia el agente bajo prueba (segundos) |

---

## Uso

### Ejecución simple

Prueba un único caso directamente:

```bash
python main.py context="El usuario quiere cancelar su suscripción" user_id=12345
```

Con modelo específico:

```bash
python main.py context="El usuario tiene un problema con su factura" user_id=99 model=gemini-2.0-flash
```

Procesar un archivo JSON en modo batch dentro de `main.py`:

```bash
python main.py json_file=cases.json batch_size=5
```

**Parámetros CLI de main.py:**

| Parámetro | Default | Descripción |
|---|---|---|
| `context` | `"No context provided."` | Contexto/escenario del caso de prueba |
| `user_id` | `"default_user"` | ID del usuario simulado |
| `model` | `$MODEL_NAME` | Modelo Gemini a usar |
| `json_file` | — | Ruta a un JSON de casos para procesar en batch |
| `batch_size` | `10` | Conversaciones concurrentes por batch (solo con `json_file`) |

---

### Batch paralelo — batch_runner.py

Para correr múltiples casos con verdadero paralelismo (subprocesos separados):

```bash
python batch_runner.py json_file=cases.json batch_size=20 max_workers=10
```

`batch_runner.py` divide `cases.json` en chunks de `batch_size`, escribe cada chunk en un archivo temporal y lanza un subproceso `python main.py` por chunk, con hasta `max_workers` en paralelo.

**Parámetros:**

| Parámetro | Default | Descripción |
|---|---|---|
| `json_file` | — | **Requerido.** Ruta al archivo JSON de casos |
| `batch_size` | `10` | Casos por subproceso |
| `max_workers` | auto | Subprocesos en paralelo (default: min(batches, cpu_count)) |
| `model` | `$MODEL_NAME` | Modelo Gemini; se reenvía a los subprocesos |

---

### Formato de cases.json

Cada elemento del array es un caso de prueba:

```json
[
  {
    "user_id": "58421687",
    "objective": "Validar la tipificación de incidencias de paquetes escolares.",
    "ScenarioGroupId": "TC005B",
    "scenario": "Ticket – Paquetes Escolares | Director | B. Tickets SDP",
    "evidence": "https://...",
    "ce": "76045",
    "prompt": "JOSÉ ANTONIO AVELAR SANDOVAL de 76045 contacta al chatbot...",
    "analysisPrompt": "Ticket creado correctamente con tipificación Administrativo > Paquetes escolares...",
    "campaigns": [
      {
        "campaign_id": "cmp-456",
        "campaign_name": "Confirmación Paquetes Escolares Q1",
        "whatsapp_template_name": "confirmacion_de_solicitud_de_paquetes_escolares_q1"
      }
    ]
  }
]
```

**Campos del caso:**

| Campo | Requerido | Descripción |
|---|---|---|
| `user_id` | Sí | ID del usuario simulado |
| `objective` | No | Objetivo de la prueba (para el análisis) |
| `ScenarioGroupId` | No | ID de grupo de escenario (ej. `TC005B`) |
| `scenario` | No | Nombre descriptivo del escenario |
| `prompt` | No | Instrucciones narrativas para el `UserAgent` |
| `analysisPrompt` | No | Criterios de éxito para el `AnalysisAgent` |
| `evidence` | No | URL de archivo de evidencia (imagen, PDF) |
| `ce` | No | Código de centro educativo |
| `campaigns` | No | Campañas WhatsApp activas durante el escenario |
| `model` | No | Override de modelo para este caso específico |

El objeto completo del caso se pasa como `context` al `UserAgent` y `AnalysisAgent`.

---

## Dashboard

Interfaz web para monitorear ejecuciones, explorar conversaciones y gestionar `cases.json`.

```bash
# Desde la raíz del proyecto
python dashboard/server.py

# Puerto personalizado
python dashboard/server.py port=9000
```

Abre **http://localhost:8765** en el navegador.

### Funcionalidades

| Sección | Descripción |
|---|---|
| **Dashboard** | Stats en tiempo real (sesiones, mensajes, insights, runs). Lista de conversaciones recientes con auto-refresh cada 5s. Botón para limpiar toda la DB. |
| **Conversaciones** | Lista paginada (20 por página) de todas las sesiones. Click en una sesión para ver el timeline completo: cada turno muestra el mensaje del usuario y la respuesta del bot. Click en el número de turno para ver el `raw_response` completo en JSON. |
| **Cases JSON** | Editor de código con validación JSON en tiempo real. Botones Formatear y Guardar. |
| **Ejecutar** | Formulario para lanzar `batch_runner.py` con `json_file`, `batch_size` y `max_workers`. Output en tiempo real via Server-Sent Events. Botón Detener: envía SIGTERM al proceso principal y ejecuta `pkill -9 -f "main.py.*batch_runner"` para limpiar subprocesos hijos. |
| **Exportar Excel** | Descarga un `.xlsx` con todos los mensajes, respuestas, `raw_response` (JSON formateado), análisis e insights. |

### Endpoints del servidor

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Sirve el dashboard HTML |
| `GET` | `/api/stats` | Conteos globales: sesiones, mensajes, insights, runs |
| `GET` | `/api/conversations` | Lista de sesiones agrupadas con metadata |
| `GET` | `/api/conversations/:id` | Mensajes + insight de una sesión |
| `DELETE` | `/api/db` | Elimina todos los logs e insights |
| `GET` | `/api/cases` | Contenido de `cases.json` |
| `PUT` | `/api/cases` | Guarda `cases.json` |
| `POST` | `/api/run` | Inicia `batch_runner.py` |
| `POST` | `/api/run/stop` | Detiene el proceso activo |
| `GET` | `/api/run/status` | Estado actual de la ejecución |
| `GET` | `/api/run/stream` | SSE: stream de output en tiempo real |
| `GET` | `/api/export/conversations` | Descarga `conversaciones.xlsx` |

> El servidor usa solo la librería estándar de Python (stdlib), sin dependencias extra.

---

## Base de datos

SQLite en `logs.db`, creado automáticamente al primer uso.

### Tabla `logs`

Cada fila es un turno de conversación (un mensaje del usuario + la respuesta del bot).

| Campo | Tipo | Descripción |
|---|---|---|
| `log_id` | INTEGER | PK autoincremental |
| `message` | TEXT | Mensaje enviado al agente externo |
| `response` | TEXT | Respuesta del agente (campo `text`) |
| `raw_response` | TEXT | JSON completo de la respuesta (doble-codificado) |
| `files` | TEXT | Adjuntos enviados (JSON array) |
| `images` | TEXT | Imágenes enviadas (JSON array) |
| `user_id` | TEXT | ID del usuario simulado |
| `session_id` | TEXT | UUID de sesión — formato `{user_id}_{fecha}` |
| `run_id` | TEXT | UUID de ejecución — agrupa todos los turnos de un caso |
| `scenario_group_id` | TEXT | ID de grupo de escenario del caso |
| `scenario` | TEXT | Nombre del escenario del caso |
| `created_at` | TEXT | Timestamp UTC de creación |
| `updated_at` | TEXT | Timestamp UTC de última actualización |

### Tabla `insights`

Análisis generado por `AnalysisAgent` al finalizar cada sesión.

| Campo | Tipo | Descripción |
|---|---|---|
| `insight_id` | INTEGER | PK autoincremental |
| `session_id` | TEXT | Sesión analizada |
| `run_id` | TEXT | Run al que pertenece |
| `analysis` | TEXT | Análisis en texto libre generado por el LLM |
| `complete` | INTEGER | `1` si la conversación cumplió su objetivo, `0` si no |
| `created_at` | TEXT | Timestamp UTC de creación |
| `updated_at` | TEXT | Timestamp UTC de última actualización |

### Query principal (Export Excel)

```sql
SELECT
  l.message,
  l.response,
  l.raw_response,
  l.files,
  l.images,
  l.user_id,
  i.analysis,
  i.complete,
  l.scenario_group_id,
  l.scenario,
  l.run_id
FROM logs l
LEFT JOIN insights i ON i.run_id = l.run_id
WHERE l.message IS NOT NULL
ORDER BY l.run_id;
```

---

## Estructura del proyecto

```
qaChatTester/
├── main.py                    # Punto de entrada; orquesta UserAgent + AnalysisAgent
├── batch_runner.py            # Lanzador paralelo de subprocesos main.py
├── cases.json                 # Casos de prueba (gitignored)
├── logs.db                    # Base de datos SQLite (gitignored)
├── pyproject.toml
├── uv.lock
│
├── agents/
│   ├── agent_base.py          # Clase base: model, tools, _build_tool()
│   ├── user.py                # UserAgent — simula al usuario con send_to_agent
│   └── analysis.py            # AnalysisAgent + AnalysisAgentManual (fallback)
│
├── tools/
│   ├── common.py              # send_to_agent, save_interaction, save_analysis
│   └── messages.py            # get_messages_by_session_id
│
├── utils/
│   ├── agent_runner.py        # Wrapper sobre Google ADK Runner con InMemorySession
│   ├── prompt_utils.py        # extract_json_blocks — parsea JSON de respuestas LLM
│   ├── tool_utils.py          # to_snake_case
│   └── built_in_func.py       # Funciones auxiliares internas
│
├── db/
│   └── sql.py                 # LogDB — singleton SQLite thread-safe con WAL
│
└── dashboard/
    ├── server.py              # Servidor HTTP stdlib: API REST + SSE
    └── index.html             # SPA dark-mode: dashboard, conversaciones, editor, runner
```

---

## API del agente bajo prueba

El agente externo debe exponer un endpoint `POST /chat`:

**Request:**
```json
{
  "account_id": "3057",
  "user_id": "12345",
  "text": "Hola, necesito ayuda con mi paquete escolar",
  "is_hsm": false,
  "hsm_name": "",
  "images": [],
  "attachments": [],
  "session_id": "abc123",
  "session_backend": "memory",
  "persist_session": false
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

**Response completa (con traces):**
```json
{
  "session_id": "abc123",
  "text": "Hola, ¿en qué puedo ayudarte?",
  "images": [],
  "messages": [
    {
      "author": "bot",
      "text": "Hola, ¿en qué puedo ayudarte?",
      "images": [],
      "metadata": { "agent": "MultiAgent", "model": "gemini/gemini-2.5-flash" }
    }
  ],
  "tool_calls": [],
  "requires_confirmation": null,
  "metadata": {},
  "traces": []
}
```

El campo `session_id` es obligatorio en la respuesta: `UserAgent` lo extrae y lo mantiene consistente a lo largo de toda la conversación. El campo `text` es el que se muestra en el dashboard como "respuesta del bot".
