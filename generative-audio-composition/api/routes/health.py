import os
import logging
from fastapi import APIRouter, HTTPException
from typing import Any

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, Any]:
    """Basic liveness check — always returns 200 if the process is up."""
    return {"status": "ok", "service": "generative-audio-composition-api"}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    """
    Readiness check.

    Verifies:
    - GPU is available (if REQUIRE_GPU is set, fails without one)
    - Redis connection is reachable
    - Model files are present on disk
    """
    checks: dict[str, Any] = {}
    errors: list[str] = []

    # --- GPU availability ---
    try:
        import torch

        gpu_available = torch.cuda.is_available()
        checks["gpu"] = {
            "available": gpu_available,
            "device_count": torch.cuda.device_count() if gpu_available else 0,
            "device_name": torch.cuda.get_device_name(0) if gpu_available else None,
        }
        require_gpu = os.getenv("REQUIRE_GPU", "false").lower() == "true"
        if require_gpu and not gpu_available:
            errors.append("GPU required but not available")
    except ImportError:
        checks["gpu"] = {"available": False, "error": "torch not installed"}

    # --- Redis connectivity ---
    try:
        import redis as redis_lib

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = {"status": "connected", "url": redis_url}
    except Exception as exc:
        checks["redis"] = {"status": "unreachable", "error": str(exc)}
        errors.append(f"Redis unreachable: {exc}")

    # --- Model files ---
    models_dir = os.getenv("MODELS_DIR", "/app/models")
    speaker_encoder_path = os.path.join(models_dir, "speaker_encoder", "model.pt")
    model_present = os.path.isfile(speaker_encoder_path)
    checks["models"] = {
        "speaker_encoder": model_present,
        "models_dir": models_dir,
    }
    if not model_present:
        logger.warning("Speaker encoder model not found at %s", speaker_encoder_path)
        # Not a hard failure — model may be downloaded lazily
        checks["models"]["warning"] = "speaker_encoder checkpoint not found; will download on first use"

    if errors:
        raise HTTPException(status_code=503, detail={"status": "not ready", "checks": checks, "errors": errors})

    return {"status": "ready", "checks": checks}
