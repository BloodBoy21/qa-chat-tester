# QA Chat Tester

Herramienta de QA automatizado para probar agentes de IA conversacionales. Usa [Google ADK](https://google.github.io/adk-docs/) con modelos Gemini para simular conversaciones completas, registrarlas en SQLite y generar un análisis automático de cada sesión.

## Arquitectura

```
main.py
├── UserAgent        → Redacta y envía mensajes al agente bajo prueba via HTTP
└── AnalysisAgent    → Analiza la conversación completa y guarda insights
```

El flujo por sesión:
1. `UserAgent` inicia la conversación enviando mensajes al endpoint `/chat` del agente bajo prueba.
2. Cada intercambio se persiste en `logs.db` (tabla `logs`).
3. Al finalizar, `AnalysisAgent` lee los mensajes de la sesión y guarda un análisis en la tabla `insights`.

## Requisitos

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (recomendado) o pip

## Instalación

```bash
# Con uv
uv sync

# Con pip
pip install -e .
```

## Variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

| Variable | Requerida | Descripción | Ejemplo |
|---|---|---|---|
| `GOOGLE_API_KEY` | Sí | API key de Google AI Studio para acceder a Gemini | `AIzaSy...` |
| `AGENT_URL` | Sí | URL base del agente bajo prueba | `https://my-agent.run.app` |
| `AGENT_TOKEN` | Sí | JWT Bearer token para autenticarse con el agente | `eyJhbG...` |
| `MODEL_NAME` | No | Modelo Gemini a usar (default: `gemini-2.5-flash`) | `gemini-2.0-flash` |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | Usar Vertex AI en lugar de AI Studio (default: `False`) | `True` |
| `APP_NAME` | No | Nombre de la app en ADK (default: `default_app_name`) | `qa-tester` |

## Uso

### Conversación simple

```bash
python main.py context="Un usuario quiere saber el precio de sus servicios" user_id=12345
```

### Con modelo específico

```bash
python main.py context="El usuario tiene un problema con su factura" user_id=99 model=gemini-2.0-flash
```

### Batch desde archivo JSON

Procesa múltiples casos de prueba en paralelo desde un archivo JSON:

```bash
python main.py json_file=casos.json batch_size=5
```

El archivo JSON debe ser una lista de objetos:

```json
[
  {
    "context": "El usuario quiere cancelar su suscripción",
    "user_id": "user_001",
    "model": "gemini-2.5-flash"
  },
  {
    "context": "El usuario pregunta por nuevos productos",
    "user_id": "user_002"
  }
]
```

**Parámetros disponibles:**

| Parámetro | Default | Descripción |
|---|---|---|
| `context` | `"No context provided."` | Escenario/instrucciones para el agente simulador |
| `user_id` | `"default_user"` | ID del usuario en la sesión |
| `model` | Valor de `MODEL_NAME` | Modelo Gemini para los agentes QA |
| `json_file` | — | Ruta a archivo JSON para modo batch |
| `batch_size` | `10` | Conversaciones concurrentes en modo batch |

## Base de datos

Se crea automáticamente el archivo `logs.db` en el directorio raíz.

**Tabla `logs`** — intercambios de la conversación:

| Campo | Tipo | Descripción |
|---|---|---|
| `log_id` | INTEGER | PK autoincremental |
| `message` | TEXT | Mensaje enviado al agente |
| `response` | TEXT | Respuesta del agente |
| `raw_response` | TEXT | Respuesta completa en JSON |
| `files` | TEXT | Adjuntos enviados (JSON) |
| `images` | TEXT | Imágenes enviadas (JSON) |
| `user_id` | TEXT | ID del usuario |
| `session_id` | TEXT | ID de sesión (`{user_id}_{fecha}`) |
| `created_at` | TEXT | Timestamp UTC |

**Tabla `insights`** — análisis generados por `AnalysisAgent`:

| Campo | Tipo | Descripción |
|---|---|---|
| `insight_id` | INTEGER | PK autoincremental |
| `session_id` | TEXT | Sesión analizada |
| `analysis` | TEXT | Análisis generado |
| `created_at` | TEXT | Timestamp UTC |

## Estructura del proyecto

```
qaChatTester/
├── main.py                  # Punto de entrada
├── agents/
│   ├── agent_base.py        # Clase base para todos los agentes
│   ├── user.py              # UserAgent — simula al usuario
│   └── analysis.py          # AnalysisAgent — analiza la sesión
├── tools/
│   ├── common.py            # send_to_agent, save_interaction, save_analysis
│   └── messages.py          # get_messages_by_session_id
├── utils/
│   ├── agent_runner.py      # Wrapper sobre Google ADK Runner
│   └── prompt_utils.py      # Helpers para parsear JSON del LLM
├── db/
│   └── sql.py               # LogDB — singleton SQLite
├── logs.db                  # Base de datos (generada automáticamente)
└── pyproject.toml
```

## API del agente bajo prueba

El agente externo debe exponer un endpoint `POST /chat` con el siguiente contrato:

**Request:**
```json
{
  "account_id": "3057",
  "user_id": "12345",
  "text": "Hola, necesito ayuda",
  "is_hsm": false,
  "hsm_name": "",
  "images": [],
  "attachments": [],
  "session_id": "",
  "session_backend": "memory",
  "persist_session": false
}
```

**Headers:**
```
Authorization: Bearer <AGENT_TOKEN>
```

**Response esperada:**
```json
{
  "text": "Respuesta del agente",
  "session_id": "abc123"
}
```
