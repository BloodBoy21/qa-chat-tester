#!/usr/bin/env python3
"""
Generate OpenAPI 3.0 spec from the FastAPI app and enhance it for Apidog.

Usage:
    uv run python scripts/export_openapi.py

Output:
    docs/openapi.json   ← import this in Apidog
    docs/openapi.yaml   ← human-readable version
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import yaml
from server.main import app

# ── 1. Get FastAPI auto-generated schema ─────────────────────────────────────

schema = app.openapi()

# ── 2. Top-level metadata ─────────────────────────────────────────────────────

schema["info"] = {
    "title": "QA Chat Tester API",
    "version": "1.0.0",
    "description": (
        "API REST para la plataforma de QA automatizado de agentes de IA conversacionales.\n\n"
        "## Autenticación\n\n"
        "La mayoría de endpoints requieren un JWT en el header `Authorization: Bearer <token>`.\n"
        "Obtén el token con `POST /v1/auth/login`.\n\n"
        "## Multi-tenancy\n\n"
        "Los endpoints de datos requieren el header `X-Account-ID: <account_id>` "
        "para identificar el tenant. Usa `GET /v1/accounts` para listar los tenants disponibles."
    ),
    "contact": {
        "name": "Nerds AI",
        "email": "it@nerds.ai",
    },
}

schema["servers"] = [
    {"url": "http://localhost:8000", "description": "Local development"},
    {"url": "https://your-api-domain.com", "description": "Production"},
]

# ── 3. Security scheme ────────────────────────────────────────────────────────

schema.setdefault("components", {})
schema["components"].setdefault("securitySchemes", {})
schema["components"]["securitySchemes"]["BearerAuth"] = {
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT",
    "description": "JWT obtenido de `POST /v1/auth/login`. Expira en 24 h.",
}

# ── 4. Reusable parameters ────────────────────────────────────────────────────

schema["components"].setdefault("parameters", {})
schema["components"]["parameters"]["AccountId"] = {
    "name": "X-Account-ID",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "example": "3057"},
    "description": "ID del tenant. Requerido en todos los endpoints de datos.",
}

# ── 5. Reusable schemas ───────────────────────────────────────────────────────

schema["components"].setdefault("schemas", {})
schema["components"]["schemas"].update({
    "PaginatedResponse": {
        "type": "object",
        "properties": {
            "items":     {"type": "array", "items": {}},
            "total":     {"type": "integer", "example": 347},
            "page":      {"type": "integer", "example": 2},
            "page_size": {"type": "integer", "example": 20},
            "pages":     {"type": "integer", "example": 18},
        },
    },
    "Error": {
        "type": "object",
        "properties": {
            "detail": {"type": "string", "example": "Token inválido o expirado"},
        },
    },
    "Account": {
        "type": "object",
        "properties": {
            "_id":         {"type": "string", "example": "664a1b2c3d4e5f6a7b8c9d0e"},
            "account_id":  {"type": "string", "example": "3057"},
            "name":        {"type": "string", "example": "Acme Corp"},
            "description": {"type": "string", "example": "Entorno de producción"},
            "created_at":  {"type": "string", "format": "date-time"},
            "updated_at":  {"type": "string", "format": "date-time"},
        },
    },
    "User": {
        "type": "object",
        "properties": {
            "user_id":              {"type": "integer", "example": 1},
            "email":                {"type": "string",  "example": "admin@empresa.com"},
            "name":                 {"type": "string",  "example": "Alan B."},
            "must_change_password": {"type": "boolean", "example": False},
        },
    },
    "TokenResponse": {
        "type": "object",
        "properties": {
            "access_token":        {"type": "string"},
            "token_type":          {"type": "string", "example": "bearer"},
            "must_change_password": {"type": "boolean", "example": False},
            "user": {"$ref": "#/components/schemas/User"},
        },
    },
    "Suite": {
        "type": "object",
        "properties": {
            "_id":         {"type": "string", "example": "664a1b2c3d4e5f6a7b8c9d0e"},
            "title":       {"type": "string", "example": "Flujo de pagos Q1"},
            "description": {"type": "string", "example": "Casos de confirmación de paquetes"},
            "case_count":  {"type": "integer", "example": 42},
            "created_at":  {"type": "string", "format": "date-time"},
            "updated_at":  {"type": "string", "format": "date-time"},
        },
    },
    "TestCase": {
        "type": "object",
        "properties": {
            "_id":         {"type": "string"},
            "suite_id":    {"type": "string"},
            "title":       {"type": "string",  "example": "Pago exitoso con tarjeta"},
            "description": {"type": "string",  "example": "Verifica respuesta del bot ante pago OK"},
            "payload":     {"type": "object",  "example": {"user_id": "58421687", "prompt": "El usuario quiere confirmar su pedido..."}},
            "created_at":  {"type": "string",  "format": "date-time"},
        },
    },
    "Run": {
        "type": "object",
        "properties": {
            "run_id":              {"type": "string",  "example": "550e8400-e29b-41d4-a716-446655440000"},
            "type":                {"type": "string",  "enum": ["suite", "case", "selection"], "example": "suite"},
            "status":              {"type": "string",  "enum": ["pending", "running", "paused", "stopped", "completed", "failed"]},
            "model":               {"type": "string",  "example": "gemini-2.5-flash"},
            "total_cases":         {"type": "integer", "example": 50},
            "completed_cases":     {"type": "integer", "example": 37},
            "failed_cases":        {"type": "integer", "example": 2},
            "conversation_run_ids": {"type": "array", "items": {"type": "string"}},
            "error":               {"type": "string",  "nullable": True},
            "created_at":          {"type": "string",  "format": "date-time"},
            "started_at":          {"type": "string",  "format": "date-time", "nullable": True},
            "finished_at":         {"type": "string",  "format": "date-time", "nullable": True},
        },
    },
    "Conversation": {
        "type": "object",
        "properties": {
            "session_id":       {"type": "string"},
            "run_id":           {"type": "string"},
            "user_id":          {"type": "string", "example": "58421687"},
            "scenario_group_id": {"type": "string", "example": "TC005B"},
            "scenario":         {"type": "string"},
            "message_count":    {"type": "integer", "example": 8},
            "started_at":       {"type": "string", "format": "date-time"},
            "last_message_at":  {"type": "string", "format": "date-time"},
            "insight_complete": {"type": "boolean", "nullable": True},
            "insight_summary":  {"type": "string",  "nullable": True},
        },
    },
    "Analysis": {
        "type": "object",
        "properties": {
            "_id":              {"type": "string"},
            "session_id":       {"type": "string"},
            "run_id":           {"type": "string"},
            "analysis":         {"type": "string", "example": "El agente confirmó exitosamente el pedido..."},
            "complete":         {"type": "boolean", "example": True},
            "user_id":          {"type": "string"},
            "scenario_group_id": {"type": "string"},
            "message_count":    {"type": "integer"},
            "created_at":       {"type": "string", "format": "date-time"},
        },
    },
})

# ── 6. Tag definitions ────────────────────────────────────────────────────────

schema["tags"] = [
    {"name": "auth",          "description": "Autenticación — login, cambio de contraseña, recuperación"},
    {"name": "accounts",      "description": "Gestión de tenants (cuentas)"},
    {"name": "stats",         "description": "Estadísticas globales del tenant"},
    {"name": "conversations", "description": "Conversaciones generadas por los agentes QA"},
    {"name": "analyses",      "description": "Insights y análisis generados por el AnalysisAgent"},
    {"name": "suites",        "description": "Test suites — contenedores de casos de prueba"},
    {"name": "cases",         "description": "Casos de prueba individuales"},
    {"name": "runs",          "description": "Ejecuciones de test suites"},
    {"name": "export",        "description": "Exportación de datos"},
]

# ── 7. Patch each path with security, headers, tags, and examples ─────────────

# Public paths — NO bearer required
PUBLIC = {
    "/v1/auth/login",
    "/v1/auth/forgot-password",
    "/v1/auth/reset-password",
}

# Paths that need Bearer but NOT X-Account-ID
BEARER_ONLY = {
    "/v1/auth/change-password",
    "/v1/auth/me",
    "/v1/accounts",
    "/v1/accounts/{account_id}",
}

# Tag mapping by path prefix
TAG_MAP = {
    "/v1/auth/":          "auth",
    "/v1/accounts":       "accounts",
    "/v1/stats":          "stats",
    "/v1/conversations":  "conversations",
    "/v1/analyses":       "analyses",
    "/v1/suites":         "suites",
    "/v1/cases/":         "cases",
    "/v1/runs/":          "runs",
    "/v1/export/":        "export",
}

ACCOUNT_ID_PARAM = {"$ref": "#/components/parameters/AccountId"}
BEARER_SECURITY  = [{"BearerAuth": []}]
PAGINATION_PARAMS = [
    {"name": "page",      "in": "query", "schema": {"type": "integer", "default": 1,  "minimum": 1}},
    {"name": "page_size", "in": "query", "schema": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200}},
]

# Per-endpoint manual overrides
ENDPOINT_META = {
    ("post",   "/v1/auth/login"): {
        "summary": "Iniciar sesión",
        "description": "Autentica al usuario y devuelve un JWT de 24 h. Si `must_change_password` es `true`, el usuario debe cambiar su contraseña antes de usar la app.",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"email": "admin@empresa.com", "password": "MiPassword1!"}}}
        },
    },
    ("post",   "/v1/auth/change-password"): {
        "summary": "Cambiar contraseña",
        "description": "Cambia la contraseña del usuario autenticado. Devuelve un nuevo JWT.",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"current_password": "TempPass1!", "new_password": "NuevaPassword2!"}}}
        },
    },
    ("post",   "/v1/auth/forgot-password"): {
        "summary": "Recuperar contraseña",
        "description": "Envía un email con un enlace de restablecimiento (expira en 1 h). Siempre devuelve `ok: true` para evitar enumeración de usuarios.",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"email": "admin@empresa.com"}}}
        },
    },
    ("post",   "/v1/auth/reset-password"): {
        "summary": "Restablecer contraseña con token",
        "description": "Establece una nueva contraseña usando el token recibido por email.",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"token": "<token_del_email>", "new_password": "NuevaPassword2!"}}}
        },
    },
    ("get",    "/v1/auth/me"): {
        "summary": "Perfil del usuario autenticado",
    },
    ("get",    "/v1/accounts"): {
        "summary": "Listar todos los tenants",
        "description": "Devuelve todos los accounts registrados. No requiere `X-Account-ID`.",
    },
    ("post",   "/v1/accounts"): {
        "summary": "Crear tenant",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"account_id": "3057", "name": "Acme Corp", "description": "Entorno de producción"}}}
        },
    },
    ("get",    "/v1/stats"): {
        "summary": "Estadísticas globales del tenant",
        "description": "Devuelve conteos de sesiones, mensajes, insights y runs para el tenant activo.",
    },
    ("get",    "/v1/conversations"): {
        "summary": "Listar conversaciones (paginado)",
        "description": "Lista paginada de conversaciones con filtros opcionales.",
        "parameters": PAGINATION_PARAMS + [
            {"name": "status",       "in": "query", "schema": {"type": "string", "enum": ["all","done","pend"],  "default": "all"}},
            {"name": "objective",    "in": "query", "schema": {"type": "string", "enum": ["all","ok","fail"],   "default": "all"}},
            {"name": "run_filter",   "in": "query", "schema": {"type": "string"}, "description": "Filtrar por suite run_id"},
            {"name": "search_field", "in": "query", "schema": {"type": "string", "enum": ["session_id","run_id","user_id","scenario","scenario_group_id"], "default": "session_id"}},
            {"name": "search_query", "in": "query", "schema": {"type": "string"}, "description": "Texto a buscar (regex, case-insensitive)"},
        ],
    },
    ("get",    "/v1/conversations/{session_id}"): {
        "summary": "Detalle de conversación",
        "description": "Devuelve los mensajes, el insight y el caso de prueba asociado a la sesión.",
    },
    ("patch",  "/v1/conversations/{session_id}/insight"): {
        "summary": "Actualizar insight manualmente",
        "description": "Marca la conversación como cumplida o fallida, o edita el texto del análisis. Si no existe insight lo crea.",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"complete": True, "analysis": "El bot cumplió el objetivo satisfactoriamente."}}}
        },
    },
    ("post",   "/v1/conversations/{session_id}/analyse"): {
        "summary": "Generar análisis con IA",
        "description": "Dispara el AnalysisAgent en background. Responde `202` inmediatamente; consulta el detalle de la conversación para ver cuándo aparece el insight.",
        "requestBody": {
            "required": False,
            "content": {"application/json": {"example": {"model": "gemini-2.5-flash"}}}
        },
    },
    ("get",    "/v1/analyses"): {
        "summary": "Listar análisis (paginado)",
        "parameters": PAGINATION_PARAMS + [
            {"name": "status", "in": "query", "schema": {"type": "string", "enum": ["all","ok","fail","pending"], "default": "all"}},
            {"name": "group",  "in": "query", "schema": {"type": "string"}, "description": "Filtrar por scenario_group_id"},
            {"name": "search", "in": "query", "schema": {"type": "string"}, "description": "Buscar en el texto del análisis"},
        ],
    },
    ("get",    "/v1/suites"): {
        "summary": "Listar test suites (paginado)",
        "parameters": PAGINATION_PARAMS,
    },
    ("post",   "/v1/suites"): {
        "summary": "Crear test suite",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"title": "Flujo de pagos Q1", "description": "Casos de confirmación de paquetes escolares"}}}
        },
    },
    ("patch",  "/v1/suites/{suite_id}"): {
        "summary": "Editar test suite",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"title": "Nuevo título", "description": "Nueva descripción"}}}
        },
    },
    ("delete", "/v1/suites/{suite_id}"): {
        "summary": "Eliminar suite y todos sus casos",
    },
    ("get",    "/v1/suites/{suite_id}/cases"): {
        "summary": "Listar casos del suite (paginado)",
        "parameters": PAGINATION_PARAMS,
    },
    ("post",   "/v1/suites/{suite_id}/cases"): {
        "summary": "Crear caso de prueba",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {
                "title": "Pago exitoso con tarjeta",
                "description": "Verifica que el bot confirme el pago",
                "payload": {
                    "user_id": "58421687",
                    "prompt": "JOSÉ ANTONIO AVELAR SANDOVAL contacta al chatbot para confirmar su paquete escolar.",
                    "analysisPrompt": "El bot debe confirmar el pedido y dar un número de seguimiento.",
                }
            }}}
        },
    },
    ("post",   "/v1/suites/{suite_id}/cases/upload"): {
        "summary": "Subir casos masivos desde JSON",
        "description": "Sube un archivo `.json` con un array de casos. Con `?replace=true` (default) reemplaza todos los casos existentes del suite.",
        "parameters": [
            {"name": "replace", "in": "query", "schema": {"type": "boolean", "default": True}, "description": "Reemplazar casos existentes"}
        ],
    },
    ("patch",  "/v1/cases/{case_id}"): {
        "summary": "Editar caso de prueba",
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": {"title": "Nuevo título", "description": "Nueva descripción", "payload": {"user_id": "123"}}}}
        },
    },
    ("delete", "/v1/cases/{case_id}"): {
        "summary": "Eliminar caso de prueba",
    },
    ("get",    "/v1/runs"): {
        "summary": "Listar ejecuciones (paginado)",
        "parameters": PAGINATION_PARAMS + [
            {"name": "suite_id", "in": "query", "schema": {"type": "string"}, "description": "Filtrar por suite"},
        ],
    },
    ("get",    "/v1/runs/{run_id}"): {
        "summary": "Detalle de ejecución",
        "description": "Incluye `conversation_run_ids` (lista de UUIDs de conversaciones generadas), progreso y estado.",
    },
    ("post",   "/v1/runs/suite/{suite_id}"): {
        "summary": "Ejecutar test suite",
        "description": (
            "Encola la ejecución del suite completo (o una selección de casos). "
            "Responde `202` inmediatamente con el `run_id`; consulta `GET /v1/runs/{run_id}` para seguir el progreso.\n\n"
            "**Escalado**: cada caso se ejecuta como un task Celery independiente en paralelo. "
            "Con 3 workers × 15 concurrencia = ~540 conversaciones/hora."
        ),
        "requestBody": {
            "required": False,
            "content": {"application/json": {"examples": {
                "todos los casos": {"value": {"model": "gemini-2.5-flash"}},
                "selección específica": {"value": {"model": "gemini-2.5-flash", "case_ids": ["664a1b2c...", "664a1b2d..."]}},
            }}}
        },
    },
    ("post",   "/v1/runs/case/{case_id}"): {
        "summary": "Ejecutar un caso individual",
        "requestBody": {
            "required": False,
            "content": {"application/json": {"example": {"model": "gemini-2.5-flash"}}}
        },
    },
    ("post",   "/v1/runs/{run_id}/pause"): {
        "summary": "Pausar ejecución",
        "description": "Los casos ya en curso terminan; el siguiente no inicia hasta reanudar.",
    },
    ("post",   "/v1/runs/{run_id}/resume"): {"summary": "Reanudar ejecución pausada"},
    ("post",   "/v1/runs/{run_id}/stop"):   {
        "summary": "Detener ejecución",
        "description": "Los casos en curso terminan; los pendientes se marcan como saltados.",
    },
    ("get",    "/v1/export/conversations"): {
        "summary": "Exportar conversaciones a Excel",
        "description": "Descarga un `.xlsx` con todas las conversaciones del tenant: mensajes, respuestas, análisis, insight y caso de prueba.",
    },
}

for path, path_item in schema.get("paths", {}).items():
    for method, op in path_item.items():
        if method not in ("get","post","put","patch","delete","options"):
            continue

        key = (method, path)

        # Apply tag
        for prefix, tag in TAG_MAP.items():
            if path.startswith(prefix):
                op["tags"] = [tag]
                break

        # Apply security + account-id header
        if path not in PUBLIC:
            op["security"] = BEARER_SECURITY

            if path not in BEARER_ONLY:
                # Add X-Account-ID to parameters
                op.setdefault("parameters", [])
                has_account_id = any(
                    p.get("name") == "X-Account-ID" or p.get("$ref", "").endswith("AccountId")
                    for p in op["parameters"]
                )
                if not has_account_id:
                    op["parameters"].insert(0, ACCOUNT_ID_PARAM)

        # Apply manual overrides
        if key in ENDPOINT_META:
            meta = ENDPOINT_META[key]
            for k, v in meta.items():
                if k == "parameters" and "parameters" in op:
                    # Merge: keep path params, replace query params with manual ones
                    path_params = [p for p in op["parameters"]
                                   if p.get("in") == "path" or p.get("$ref", "").endswith("AccountId")]
                    op["parameters"] = path_params + [p for p in v if p.get("in") != "path"]
                else:
                    op[k] = v

        # Standard 401/404 responses
        op.setdefault("responses", {})
        if path not in PUBLIC:
            op["responses"]["401"] = {
                "description": "No autenticado o token expirado",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            }
        if "{" in path:
            op["responses"]["404"] = {
                "description": "Recurso no encontrado",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            }

# ── 8. Write output ───────────────────────────────────────────────────────────

out_dir = Path(__file__).parent.parent / "docs"
out_dir.mkdir(exist_ok=True)

json_path = out_dir / "openapi.json"
yaml_path = out_dir / "openapi.yaml"

json_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"✓ docs/openapi.json  ({json_path.stat().st_size // 1024} KB)")

yaml_path.write_text(yaml.dump(schema, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
print(f"✓ docs/openapi.yaml  ({yaml_path.stat().st_size // 1024} KB)")

print()
print("Importa docs/openapi.json en Apidog:")
print("  Apidog → Import → OpenAPI / Swagger → selecciona el archivo")
