import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from lib.cache import get_cache
from lib.mongo import client as mongo_client, db as mongo_db
from lib.sql_db import init_db
from db.repositories import setup_indexes
from pyrate_limiter import Duration, Limiter, Rate
from fastapi_limiter.depends import RateLimiter


origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

IS_PRODUCTION = os.getenv("ENV", "development") == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    logger.info("Setting up cache")
    cache = get_cache()
    logger.info(f"Cache: {cache.ping()}")
    logger.info("Setting up SQL tables")
    init_db()
    logger.info("Setting up MongoDB indexes")
    setup_indexes(mongo_db)
    yield
    mongo_client.close()
    logger.info("Shutting down")


app = FastAPI(
    title="QA Chat Tester API",
    description="The API for the QA Chat Tester application, which allows users to test and analyze chatbot conversations.",
    version="0.1",
    lifespan=lifespan,
    docs_url="/docs" if not IS_PRODUCTION else None,
    redoc_url="/redoc" if not IS_PRODUCTION else None,
    openapi_url="/openapi.json" if not IS_PRODUCTION else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/",
    dependencies=[Depends(RateLimiter(limiter=Limiter(Rate(2, Duration.MINUTE * 5))))],
)
async def index():
    return {"message": "Welcome to the QA Chat Tester API"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    app = app if IS_PRODUCTION else "server.main:app"
    uvicorn.run(
        app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=not IS_PRODUCTION
    )
