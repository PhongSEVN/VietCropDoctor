"""
Vision-AI microservice — FastAPI entry point.

Endpoints: /predict  /health  /diseases
"""
import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import io

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from PIL import Image
from prometheus_fastapi_instrumentator import Instrumentator

from vcd_shared.kafka import (
    TOPIC_DISEASE_DETECTED,
    KafkaProducer,
)
from vcd_shared.logging import setup_logging
from vcd_shared.schemas import DiseasesResponse, HealthResponse, PredictResult
from app import cv_service
from app.admin_routes import router as admin_router
from app.config import ALLOWED_IMAGE_TYPES, CORS_ORIGINS, JWT_SECRET, JWT_ALGORITHM, MAX_IMAGE_SIZE
from app.metrics import (
    ensemble_predictions_total,
    model_confidence,
    prediction_latency,
    predictions_total,
)
from app.minio_client import upload_image
from app.state import app_state

logger = logging.getLogger("vision_ai.main")

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _user_id_from_token(token: str | None) -> str:
    if not token:
        return ""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return str(payload.get("sub", ""))
    except JWTError:
        return ""

_producer: KafkaProducer | None = None
_producer_task: asyncio.Task | None = None

_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
]


def _check_magic_bytes(data: bytes) -> bool:
    for magic, _ in _MAGIC_BYTES:
        if data[:len(magic)] == magic:
            if magic == b"RIFF":
                return data[8:12] == b"WEBP"
            return True
    return False


def validate_and_sanitize_image(contents: bytes) -> bytes:
    """Enforce size, magic bytes, MIME, and strip EXIF. Returns clean JPEG bytes."""
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds maximum allowed size of {MAX_IMAGE_SIZE // (1024 * 1024)} MB",
        )

    if not _check_magic_bytes(contents):
        raise HTTPException(
            status_code=400,
            detail="Invalid image format: magic bytes do not match JPEG, PNG, or WebP",
        )

    try:
        img = Image.open(io.BytesIO(contents))
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=b"", icc_profile=None)
        return buf.getvalue()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot decode image: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _producer, _producer_task
    setup_logging(level="INFO")
    logger.info("=" * 55)
    logger.info("Starting VietCropDoctor Vision-AI")
    logger.info("=" * 55)
    cv_service.load_cv_model()

    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    _producer = KafkaProducer(bootstrap_servers=bootstrap, service="vision-ai")
    # Connect in the background so a slow/unavailable broker never blocks
    # startup; the producer self-heals (retries with backoff) and predictions
    # keep working without Kafka in the meantime — see `_producer.connected`.
    _producer_task = asyncio.create_task(_producer.start(), name="kafka-producer-connect")

    logger.info("Vision-AI ready.")
    yield
    logger.info("Vision-AI shutting down.")
    if _producer_task:
        _producer_task.cancel()
        try:
            await _producer_task
        except (asyncio.CancelledError, Exception):
            pass
    if _producer:
        await _producer.stop()


app = FastAPI(
    title="VietCropDoctor Vision-AI",
    version="1.0.0",
    description="Plant disease detection service for Vietnamese crops",
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

app.include_router(admin_router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.post("/predict", response_model=PredictResult, tags=["prediction"])
async def predict(
    image: UploadFile = File(...),
    x_user_id: str = Header(default="", alias="X-User-Id"),
    authorization: str = Header(default="", alias="Authorization"),
):
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are supported")
    contents = await image.read()
    contents = validate_and_sanitize_image(contents)

    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else None
    user_id = x_user_id or _user_id_from_token(token)

    t0 = time.perf_counter()
    try:
        result = await asyncio.to_thread(cv_service.predict, contents)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Không xử lý được ảnh: {exc}")
    elapsed = time.perf_counter() - t0

    prediction_latency.observe(elapsed)
    # Crop type derived from the canonical class name "Crop_benh_..." (cafe|lua|mia|ngo).
    crop_type = result["disease"].split("_")[0].lower() or "unknown"
    predictions_total.labels(
        disease=result["disease"],
        severity=result.get("severity", "unknown"),
        crop_type=crop_type,
    ).inc()
    model_confidence.labels(disease=result["disease"]).set(result["confidence"])
    # Per-model prediction rate within the ensemble (drives the Grafana ensemble panel).
    for pm in result.get("per_model_predictions", []):
        ensemble_predictions_total.labels(model=pm.get("name", "unknown")).inc()

    image_id = str(uuid.uuid4())
    image_path = await upload_image(contents, image_id, result["disease"])

    if _producer and _producer.connected:
        try:
            await _producer.publish(
                topic=TOPIC_DISEASE_DETECTED,
                event_type="disease.detected",
                payload={
                    "disease":        result["disease"],
                    "confidence":     result["confidence"],
                    "severity":       result.get("severity", ""),
                    "agreement_score": result.get("agreement_score", 1.0),
                    "ensemble_used":  result.get("ensemble_used", False),
                    "top3":           result["top3"],
                    "image_id":       image_id,
                    "filename":       image.filename,
                    "image_path":     image_path,
                    "user_id":        user_id,
                },
            )
        except Exception:
            logger.warning("Failed to publish disease.detected event", exc_info=True)

    return PredictResult(**result, image_url=image_path)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health():
    return HealthResponse(
        status="ok",
        model_loaded=app_state.model_loaded,
        kafka_connected=bool(_producer and _producer.connected),
    )


@app.get("/diseases", response_model=DiseasesResponse, tags=["system"])
def diseases():
    return DiseasesResponse(diseases=app_state.class_names)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
