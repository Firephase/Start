"""
Generative Audio Composition API
=================================
FastAPI application entry point.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.routes.generate import router as generate_router
from api.routes.health import router as health_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log startup / shutdown events and perform any one-time initialisation."""
    import os

    logger.info("=" * 60)
    logger.info("Generative Audio Composition API starting up")
    logger.info("  UPLOAD_DIR  : %s", os.getenv("UPLOAD_DIR", "/tmp/audio_uploads"))
    logger.info("  OUTPUT_DIR  : %s", os.getenv("OUTPUT_DIR", "/tmp/audio_outputs"))
    logger.info("  MODELS_DIR  : %s", os.getenv("MODELS_DIR", "/app/models"))
    logger.info("  REDIS_URL   : %s", os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # Check GPU availability (informational only — never blocks startup)
    try:
        import torch

        if torch.cuda.is_available():
            logger.info("  GPU         : %s", torch.cuda.get_device_name(0))
        else:
            logger.warning("  GPU         : not available — inference will run on CPU")
    except ImportError:
        logger.warning("  GPU         : torch not installed; GPU check skipped")

    logger.info("=" * 60)

    yield

    logger.info("Generative Audio Composition API shutting down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Generative Audio Composition API",
    description="Transform amateur vocal recordings into professional music tracks",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production via ALLOWED_ORIGINS env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique ``X-Request-ID`` header to every request and response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Store on request state so route handlers can access it
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"

        logger.info(
            "%s %s -> %s [%.2fms] rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response


app.add_middleware(RequestIDMiddleware)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a clean 422 with structured error details."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "detail": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(413)
async def request_entity_too_large_handler(
    request: Request, exc: Any
) -> JSONResponse:
    """Friendly message when the client sends a body that exceeds the server limit."""
    return JSONResponse(
        status_code=413,
        content={
            "error": "Request entity too large",
            "detail": (
                "The uploaded content exceeds the maximum allowed size. "
                "Each audio file must be ≤ 3 minutes and the total request body "
                "must be ≤ 500 MB."
            ),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(415)
async def unsupported_media_type_handler(
    request: Request, exc: Any
) -> JSONResponse:
    """Friendly 415 when an unsupported audio format is uploaded."""
    return JSONResponse(
        status_code=415,
        content={
            "error": "Unsupported media type",
            "detail": (
                "Accepted audio formats: wav, mp3, m4a, ogg, flac. "
                "Please convert your file and try again."
            ),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler to avoid leaking stack traces to clients."""
    logger.exception(
        "Unhandled exception for %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. Please try again later.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health_router)
app.include_router(generate_router)
