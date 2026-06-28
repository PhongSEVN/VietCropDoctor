"""
Admin endpoints for vision-ai.

POST /admin/reload-model  — hot-reload the CV model from disk
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from app import cv_service, model_sync
from app.config import CKPT_PATH
from app.state import app_state

logger = logging.getLogger("vision_ai.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reload-model")
async def reload_model(sync: bool = Query(default=True)):
    """Hot-swap the CV model (or ensemble) without restarting the service.

    When ``sync`` is true (the default, used by the retrain DAG), promoted weights
    are first pulled from MLflow into cv/results/ so the freshly trained models are
    actually served. The pull is best-effort per model and never blocks the reload.
    """
    logger.info("Admin: reload-model requested (sync=%s)", sync)
    try:
        sync_summary = None
        if sync:
            sync_summary = await asyncio.to_thread(model_sync.sync_promoted_models)

        # Reset stale state so load_cv_model() starts clean
        app_state.model = None
        app_state.ensemble = None
        app_state.model_loaded = False

        await asyncio.to_thread(cv_service.load_cv_model)

        checkpoint = str(CKPT_PATH) if CKPT_PATH.exists() else "ensemble/mock"
        logger.info("Admin: reload-model complete (checkpoint=%s)", checkpoint)
        return {
            "status":       "reloaded",
            "checkpoint":   checkpoint,
            "classes":      len(app_state.class_names),
            "model_loaded": app_state.model_loaded,
            "model_sync":   sync_summary,
        }
    except Exception as exc:
        logger.exception("Admin: reload-model failed")
        raise HTTPException(status_code=500, detail=f"Reload failed: {exc}")
