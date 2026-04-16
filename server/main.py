import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from lib.cache import get_cache
from lib.mongo import client as mongo_client, db as mongo_db
from lib.sql_db import init_db
from db.repositories import setup_indexes
from server.api import api_router
from pyrate_limiter import Duration, Limiter, Rate
from fastapi_limiter.depends import RateLimiter

# ── Config ────────────────────────────────────────────────────────────────────

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
IS_PRODUCTION = os.getenv("ENV", "development") == "production"

if not IS_PRODUCTION:
    origins = ["*"]

# Exact paths that never require a JWT
_PUBLIC_PATHS = {
    "/v1/auth/login",
    "/v1/auth/forgot-password",
    "/v1/auth/reset-password",
    "/health",
    "/",
}

# Prefix-matched public paths (docs, etc.)
_PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    cache = get_cache()
    logger.info(f"Cache ping: {cache.ping()}")
    init_db()
    logger.info("SQL tables ready")
    setup_indexes(mongo_db)
    logger.info("MongoDB indexes ready")
    yield
    mongo_client.close()
    logger.info("Shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="QA Chat Tester API",
    description="QA automation platform for conversational AI agents.",
    version="0.1",
    lifespan=lifespan,
    docs_url="/docs"       if not IS_PRODUCTION else None,
    redoc_url="/redoc"     if not IS_PRODUCTION else None,
    openapi_url="/openapi.json" if not IS_PRODUCTION else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth middleware ────────────────────────────────────────────────────────────

def _cors_headers(request: Request) -> dict:
    """CORS headers to attach to direct error responses from this middleware."""
    origin = request.headers.get("origin", "*")
    allowed = origins if origins != ["*"] else [origin]
    return {
        "Access-Control-Allow-Origin":  origin if (origins == ["*"] or origin in origins) else "",
        "Access-Control-Allow-Headers": "*",
        "WWW-Authenticate":             "Bearer",
    }


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # CORS pre-flight: always let it through so CORSMiddleware can respond
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    # Public routes — no token required
    if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    # Validate Bearer token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            {"detail": "Not authenticated"},
            status_code=401,
            headers=_cors_headers(request),
        )

    token = auth_header.split(" ", 1)[1]
    from lib.auth import verify_access_token
    payload = verify_access_token(token)
    if not payload:
        return JSONResponse(
            {"detail": "Token inválido o expirado"},
            status_code=401,
            headers=_cors_headers(request),
        )

    request.state.user = payload
    return await call_next(request)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get(
    "/",
    dependencies=[Depends(RateLimiter(limiter=Limiter(Rate(2, Duration.MINUTE * 5))))],
)
async def index():
    return {"message": "QA Chat Tester API"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    app_ref = app if IS_PRODUCTION else "server.main:app"
    uvicorn.run(app_ref, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=not IS_PRODUCTION)
