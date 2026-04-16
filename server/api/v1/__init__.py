from fastapi import APIRouter

from server.api.v1 import accounts, analyses, cases, conversations, export, runs, stats, suites

v1_router = APIRouter()

v1_router.include_router(accounts.router)
v1_router.include_router(stats.router)
v1_router.include_router(conversations.router)
v1_router.include_router(analyses.router)
v1_router.include_router(suites.router)
v1_router.include_router(cases.router)
v1_router.include_router(runs.router)
v1_router.include_router(export.router)
