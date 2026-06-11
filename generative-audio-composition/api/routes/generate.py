import json
import logging
import mimetypes
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any

import redis as redis_lib
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from api.schemas.models import (
    GenerateRequest,
    GenerateResponse,
    JobResult,
    JobStatus,
    OutputFormat,
    SongSection,
)
from api.workers.tasks import celery_app, generate_track

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generation"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
MAX_FILE_DURATION_SECONDS = 180.0  # 3 minutes
MAX_FILES = 10
MIN_FILES = 1

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/audio_uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/audio_outputs"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_redis() -> redis_lib.Redis:
    return redis_lib.from_url(REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_extension(filename: str) -> str:
    """Return lowercased extension or raise HTTPException."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    return ext


def _get_audio_duration(path: Path) -> float:
    """Return duration in seconds using soundfile or mutagen as fallback."""
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return info.duration
    except Exception:
        pass
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(path))
        if audio is not None and audio.info is not None:
            return float(audio.info.length)
    except Exception:
        pass
    # If we cannot determine duration, let the worker handle validation
    return 0.0


def _store_job_meta(r: redis_lib.Redis, job_id: str, meta: dict[str, Any]) -> None:
    r.set(f"job:{job_id}:meta", json.dumps(meta), ex=86400)


def _load_job_meta(r: redis_lib.Redis, job_id: str) -> dict[str, Any] | None:
    raw = r.get(f"job:{job_id}:meta")
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit audio files for composition",
)
async def generate(
    files: Annotated[
        list[UploadFile],
        File(description="1–10 audio files (wav/mp3/m4a/ogg/flac, each ≤ 3 minutes)"),
    ],
    target_duration: Annotated[
        float,
        Form(ge=30.0, le=480.0, description="Target output duration in seconds"),
    ] = 180.0,
    structure: Annotated[
        str | None,
        Form(description='JSON array of song sections, e.g. ["intro","verse","chorus"]'),
    ] = None,
    genre: Annotated[
        str | None,
        Form(max_length=50, description="Genre hint"),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        Form(description="Output format: wav or mp3"),
    ] = OutputFormat.wav,
) -> GenerateResponse:
    """
    Accept 1–10 vocal recordings and schedule a composition job.

    Returns a ``job_id`` that can be polled via ``GET /jobs/{job_id}``.
    """
    # --- Validate file count ---
    if len(files) < MIN_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At least {MIN_FILES} audio file is required.",
        )
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No more than {MAX_FILES} audio files are allowed per request.",
        )

    # --- Parse structure ---
    parsed_structure: list[SongSection] | None = None
    if structure is not None:
        try:
            raw_sections = json.loads(structure)
            parsed_structure = [SongSection(s) for s in raw_sections]
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid structure JSON: {exc}",
            )

    # Build and validate the request object
    try:
        request = GenerateRequest(
            target_duration=target_duration,
            structure=parsed_structure,
            genre=genre,
            output_format=output_format,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # --- Save uploaded files ---
    job_id = str(uuid.uuid4())
    job_upload_dir = UPLOAD_DIR / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    try:
        for idx, upload in enumerate(files):
            filename = upload.filename or f"audio_{idx}"
            ext = _validate_extension(filename)
            dest = job_upload_dir / f"input_{idx:02d}{ext}"

            # Stream to disk
            with dest.open("wb") as fh:
                while True:
                    chunk = await upload.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    fh.write(chunk)

            # Validate duration
            duration = _get_audio_duration(dest)
            if duration > MAX_FILE_DURATION_SECONDS:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"File '{filename}' is {duration:.1f}s long; "
                        f"maximum allowed is {MAX_FILE_DURATION_SECONDS:.0f}s (3 minutes)."
                    ),
                )

            saved_paths.append(str(dest))

    except HTTPException:
        shutil.rmtree(job_upload_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(job_upload_dir, ignore_errors=True)
        logger.exception("Failed to save uploaded files for job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded files: {exc}",
        )

    # --- Store initial metadata in Redis ---
    from datetime import datetime, timezone

    created_at = datetime.now(timezone.utc).isoformat()
    meta: dict[str, Any] = {
        "job_id": job_id,
        "status": JobStatus.pending.value,
        "created_at": created_at,
        "params": request.model_dump(mode="json"),
        "input_paths": saved_paths,
    }
    try:
        r = _get_redis()
        _store_job_meta(r, job_id, meta)
    except Exception as exc:
        shutil.rmtree(job_upload_dir, ignore_errors=True)
        logger.exception("Redis unavailable while creating job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not persist job metadata: {exc}",
        )

    # --- Enqueue Celery task ---
    params = request.model_dump(mode="json")
    generate_track.apply_async(
        args=[job_id, saved_paths, params],
        task_id=job_id,
        queue="audio_generation",
    )

    logger.info("Job %s enqueued with %d file(s)", job_id, len(saved_paths))
    return GenerateResponse(
        job_id=job_id,
        status=JobStatus.pending,
        message="Job accepted and queued for processing.",
    )


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}",
    response_model=JobResult,
    summary="Poll job status and retrieve result",
)
async def get_job(job_id: str) -> JobResult:
    """Return current status and (when complete) result metadata for a job."""
    try:
        r = _get_redis()
        meta = _load_job_meta(r, job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        )

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    raw_status = meta.get("status", JobStatus.pending.value)
    job_status = JobStatus(raw_status)

    download_url: str | None = None
    if job_status == JobStatus.completed:
        output_format = meta.get("params", {}).get("output_format", "wav")
        output_file = OUTPUT_DIR / f"{job_id}.{output_format}"
        if output_file.exists():
            download_url = f"/jobs/{job_id}/download"

    return JobResult(
        job_id=job_id,
        status=job_status,
        download_url=download_url,
        lyrics=meta.get("lyrics"),
        key=meta.get("key"),
        bpm=meta.get("bpm"),
        genre=meta.get("genre"),
        structure=meta.get("structure"),
        duration=meta.get("duration"),
        error=meta.get("error"),
        created_at=meta.get("created_at"),
        completed_at=meta.get("completed_at"),
    )


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/download
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/download",
    summary="Stream the completed audio file",
)
async def download_job(job_id: str) -> FileResponse:
    """Stream the generated audio file to the client."""
    try:
        r = _get_redis()
        meta = _load_job_meta(r, job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        )

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    job_status = JobStatus(meta.get("status", JobStatus.pending.value))
    if job_status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is not yet complete (status: {job_status.value}).",
        )

    output_format = meta.get("params", {}).get("output_format", "wav")
    output_file = OUTPUT_DIR / f"{job_id}.{output_format}"

    if not output_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Output file for job '{job_id}' not found on disk.",
        )

    media_type = "audio/wav" if output_format == "wav" else "audio/mpeg"
    return FileResponse(
        path=str(output_file),
        media_type=media_type,
        filename=f"composition_{job_id}.{output_format}",
    )


# ---------------------------------------------------------------------------
# DELETE /jobs/{job_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Cancel or delete a job",
)
async def delete_job(job_id: str) -> dict[str, str]:
    """
    Cancel a pending/processing job or remove a completed/failed job's data.

    - If the job is still pending or processing, it is revoked in Celery.
    - Upload and output files are removed from disk.
    - Metadata is deleted from Redis.
    """
    try:
        r = _get_redis()
        meta = _load_job_meta(r, job_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        )

    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    job_status = JobStatus(meta.get("status", JobStatus.pending.value))

    # Revoke celery task if still active
    if job_status in (JobStatus.pending, JobStatus.processing):
        try:
            celery_app.control.revoke(job_id, terminate=True, signal="SIGKILL")
            logger.info("Revoked Celery task %s", job_id)
        except Exception as exc:
            logger.warning("Could not revoke Celery task %s: %s", job_id, exc)

    # Remove upload directory
    job_upload_dir = UPLOAD_DIR / job_id
    if job_upload_dir.exists():
        shutil.rmtree(job_upload_dir, ignore_errors=True)

    # Remove output files
    for ext in ("wav", "mp3"):
        output_file = OUTPUT_DIR / f"{job_id}.{ext}"
        if output_file.exists():
            output_file.unlink(missing_ok=True)

    # Remove Redis key
    r.delete(f"job:{job_id}:meta")

    return {"job_id": job_id, "message": "Job deleted successfully."}
