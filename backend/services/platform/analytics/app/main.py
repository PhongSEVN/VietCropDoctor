"""
Analytics microservice — FastAPI entry point.

Endpoints: /analytics/summary  /analytics/disease-trend
           /analytics/crop-distribution  /analytics/severity-breakdown
           /analytics/alerts  /health
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from vcd_shared.logging import setup_logging
from app import consumer
from app.api import router as analytics_router
from app.config import CORS_ORIGINS
from app.queries import init_schema

logger = logging.getLogger("analytics.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level="INFO")
    logger.info("Analytics service starting")

    await init_schema()
    await consumer.start()

    logger.info("Analytics service ready")
    yield
    logger.info("Analytics service shutting down")

    await consumer.stop()


app = FastAPI(
    title="VietCropDoctor Analytics",
    version="1.0.0",
    description="OLAP analytics over prediction and chat events",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analytics_router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "analytics", "kafka": consumer.kafka_status()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8004, reload=True)
