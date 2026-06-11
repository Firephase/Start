"""
Celery worker tasks for generative audio composition.

Task flow:
    PENDING -> STARTED -> SUCCESS / FAILURE
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celery import Celery, states
from celery.exceptions import Ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------

celery_app = Celery(
    "audio_composer",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={"generate_track": {"queue": "audio_generation"}},
    result_expires=86400,  # 24 hours
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/audio_outputs"))
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Redis helpers (sync)
# ---------------------------------------------------------------------------


def _get_redis():
    import redis as redis_lib

    return redis_lib.from_url(REDIS_URL, decode_responses=True)


def _update_job_meta(job_id: str, updates: dict[str, Any]) -> None:
    """Merge ``updates`` into the stored job metadata atomically."""
    try:
        r = _get_redis()
        key = f"job:{job_id}:meta"
        raw = r.get(key)
        meta: dict[str, Any] = json.loads(raw) if raw else {"job_id": job_id}
        meta.update(updates)
        r.set(key, json.dumps(meta), ex=86400)
    except Exception as exc:
        logger.warning("Could not update Redis metadata for job %s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Pipeline lazy import helper
# ---------------------------------------------------------------------------


def _load_pipeline(params: dict[str, Any]):
    """
    Import and instantiate the AudioPipeline from core.pipeline.

    We import lazily inside the task so the Celery worker process can start
    even if heavy ML dependencies have not fully initialised yet.
    """
    try:
        from core.pipeline import AudioPipeline, PipelineConfig  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "core.pipeline module not found. "
            "Ensure the core package is installed and PYTHONPATH is set correctly."
        ) from exc

    config = PipelineConfig(
        models_dir=str(MODELS_DIR),
        output_format=params.get("output_format", "wav"),
        target_duration=params.get("target_duration", 180.0),
        genre=params.get("genre"),
        structure=params.get("structure"),
        device=os.getenv("TORCH_DEVICE", "cuda" if _cuda_available() else "cpu"),
    )
    return AudioPipeline(config)


def _cuda_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="generate_track",
    time_limit=360,
    soft_time_limit=300,
    max_retries=0,
)
def generate_track(
    self,
    job_id: str,
    audio_paths: list[str],
    params: dict[str, Any],
) -> dict[str, Any]:
    """
    Run the full AudioPipeline to generate a composed track.

    Parameters
    ----------
    job_id:
        Unique job identifier (also used as the Celery task ID).
    audio_paths:
        List of absolute paths to the uploaded input audio files.
    params:
        Serialised ``GenerateRequest`` dict (output of ``model.model_dump()``).

    Returns
    -------
    dict
        Metadata dict that is also stored in Redis and surfaced via the API.
    """
    logger.info("Starting generate_track for job %s", job_id)

    # Mark job as processing
    _update_job_meta(
        job_id,
        {
            "status": "processing",
            "task_id": self.request.id,
            "worker": self.request.hostname,
        },
    )
    self.update_state(state=states.STARTED, meta={"job_id": job_id, "stage": "loading_pipeline"})

    output_format = params.get("output_format", "wav")
    output_path = OUTPUT_DIR / f"{job_id}.{output_format}"

    try:
        # --- Load pipeline ---
        self.update_state(state=states.STARTED, meta={"job_id": job_id, "stage": "loading_pipeline"})
        pipeline = _load_pipeline(params)
        logger.info("Pipeline loaded for job %s", job_id)

        # --- Run pipeline ---
        self.update_state(state=states.STARTED, meta={"job_id": job_id, "stage": "composing"})
        result = pipeline.run(
            input_paths=[str(p) for p in audio_paths],
            output_path=str(output_path),
            job_id=job_id,
            progress_callback=lambda stage, pct: self.update_state(
                state=states.STARTED,
                meta={"job_id": job_id, "stage": stage, "progress": pct},
            ),
        )

        # --- Collect output metadata ---
        completed_at = datetime.now(timezone.utc).isoformat()
        meta_update: dict[str, Any] = {
            "status": "completed",
            "completed_at": completed_at,
            "output_path": str(output_path),
            "lyrics": result.get("lyrics"),
            "key": result.get("key"),
            "bpm": result.get("bpm"),
            "genre": result.get("genre"),
            "structure": result.get("structure"),
            "duration": result.get("duration"),
        }
        _update_job_meta(job_id, meta_update)
        logger.info("Job %s completed successfully. Output: %s", job_id, output_path)

        return meta_update

    except Exception as exc:
        error_msg = str(exc)
        tb = traceback.format_exc()
        logger.error("Job %s failed: %s\n%s", job_id, error_msg, tb)

        failed_at = datetime.now(timezone.utc).isoformat()
        _update_job_meta(
            job_id,
            {
                "status": "failed",
                "error": error_msg,
                "traceback": tb,
                "completed_at": failed_at,
            },
        )

        # Update Celery state to FAILURE so the backend reflects it
        self.update_state(
            state=states.FAILURE,
            meta={
                "job_id": job_id,
                "error": error_msg,
                "exc_type": type(exc).__name__,
            },
        )
        raise Ignore()  # Prevent Celery from overwriting our custom FAILURE state

    finally:
        # Always clean up uploaded input files
        _cleanup_input_files(job_id, audio_paths)


def _cleanup_input_files(job_id: str, audio_paths: list[str]) -> None:
    """Remove the per-job upload directory that holds input audio files."""
    if not audio_paths:
        return
    # The upload dir is the common parent of all input files
    try:
        first_parent = Path(audio_paths[0]).parent
        # Safety check: only remove if the directory name matches the job_id
        if first_parent.name == job_id and first_parent.exists():
            shutil.rmtree(str(first_parent), ignore_errors=True)
            logger.debug("Cleaned up upload directory %s for job %s", first_parent, job_id)
        else:
            # Fall back to removing individual files
            for path in audio_paths:
                p = Path(path)
                if p.exists():
                    p.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to clean up input files for job %s: %s", job_id, exc)
