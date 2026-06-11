"""Integration tests for the REST API."""

import io
import json
import numpy as np
import pytest
import soundfile as sf
from unittest.mock import patch, MagicMock


def make_wav_bytes(duration: float = 2.0, sr: int = 44100) -> bytes:
    """Create a minimal WAV file in memory."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    buf.seek(0)
    return buf.read()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


@pytest.fixture
def mock_celery_task():
    """Mock Celery task to avoid actual GPU processing in tests."""
    with patch("api.routes.generate.generate_track") as mock:
        mock.delay.return_value = MagicMock(id="test-job-123")
        yield mock


class TestHealthEndpoints:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_ready_returns_200_or_503(self, client):
        resp = client.get("/ready")
        assert resp.status_code in (200, 503)


class TestGenerateEndpoint:
    def test_generate_requires_files(self, client, mock_celery_task):
        resp = client.post("/generate")
        assert resp.status_code == 422

    def test_generate_accepts_valid_wav(self, client, mock_celery_task):
        wav_bytes = make_wav_bytes(duration=5.0)
        resp = client.post(
            "/generate",
            files=[("audio_files", ("test.wav", wav_bytes, "audio/wav"))],
            data={"target_duration": "180", "output_format": "wav"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_generate_rejects_too_many_files(self, client, mock_celery_task):
        files = [
            ("audio_files", (f"test{i}.wav", make_wav_bytes(1.0), "audio/wav"))
            for i in range(12)
        ]
        resp = client.post("/generate", files=files)
        assert resp.status_code == 422

    def test_generate_accepts_structure_param(self, client, mock_celery_task):
        wav_bytes = make_wav_bytes(duration=5.0)
        structure = json.dumps(["verse", "chorus", "verse", "chorus"])
        resp = client.post(
            "/generate",
            files=[("audio_files", ("test.wav", wav_bytes, "audio/wav"))],
            data={"target_duration": "180", "structure": structure},
        )
        assert resp.status_code == 202

    def test_generate_rejects_invalid_format(self, client, mock_celery_task):
        resp = client.post(
            "/generate",
            files=[("audio_files", ("test.exe", b"INVALID", "application/octet-stream"))],
        )
        assert resp.status_code == 415


class TestJobStatusEndpoint:
    def test_unknown_job_returns_404(self, client):
        resp = client.get("/jobs/nonexistent-job-id")
        assert resp.status_code == 404

    def test_job_status_structure(self, client):
        # Mock Redis to return a known job
        with patch("api.routes.generate.get_job_status") as mock_status:
            mock_status.return_value = {
                "job_id": "abc123",
                "status": "completed",
                "download_url": "/jobs/abc123/download",
                "lyrics": "Sample lyrics",
                "key": "C major",
                "bpm": 120.0,
                "duration": 180.0,
            }
            resp = client.get("/jobs/abc123")
            assert resp.status_code == 200
            data = resp.json()
            assert data["job_id"] == "abc123"
            assert data["status"] == "completed"
