from pydantic import BaseModel, Field, validator
from typing import Optional
from enum import Enum


class OutputFormat(str, Enum):
    wav = "wav"
    mp3 = "mp3"


class SongSection(str, Enum):
    intro = "intro"
    verse = "verse"
    pre_chorus = "pre-chorus"
    chorus = "chorus"
    bridge = "bridge"
    outro = "outro"


class GenerateRequest(BaseModel):
    target_duration: float = Field(
        default=180.0,
        ge=30.0,
        le=480.0,
        description="Target track duration in seconds",
    )
    structure: Optional[list[SongSection]] = Field(
        default=None,
        description="Song structure. None = auto-detect",
    )
    genre: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Genre hint: pop, rock, folk, r&b, etc.",
    )
    output_format: OutputFormat = OutputFormat.wav


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    download_url: Optional[str] = None
    lyrics: Optional[str] = None
    key: Optional[str] = None
    bpm: Optional[float] = None
    genre: Optional[str] = None
    structure: Optional[list[str]] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
