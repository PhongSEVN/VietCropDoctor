"""
Auth microservice — FastAPI entry point.

Endpoints: /auth/register  /auth/login  /auth/refresh
           /auth/me        /auth/set-cookie  /auth/logout
           /auth/_validate  /auth/_validate/admin  /auth/_validate/agronomist
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from vcd_shared.logging import setup_logging
from app.config import get_settings
from app.database import close_pool, init_pool, run_migrations
from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router

logger = logging.getLogger("auth.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level=get_settings().log_level)
    logger.info("=" * 55)
    logger.info("Starting VietCropDoctor Auth Service")
    logger.info("=" * 55)

    pool = await init_pool()
    await run_migrations(pool)
    logger.info("Auth service ready.")
    yield
    await close_pool()
    logger.info("Auth service shut down.")


settings = get_settings()

app = FastAPI(
    title="VietCropDoctor Auth",
    version="1.0.0",
    description="Authentication and authorisation microservice",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "auth"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8005, reload=True)
