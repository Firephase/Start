from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Paths
    upload_dir: str = "/tmp/gac/uploads"
    output_dir: str = "/tmp/gac/outputs"
    models_dir: str = "/models"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_task_time_limit: int = 360  # 6 minutes hard limit
    celery_task_soft_time_limit: int = 300  # 5 minutes soft limit

    # Model paths (override with actual checkpoints)
    diffsinger_path: str = ""
    speaker_encoder_path: str = ""
    musicgen_path: str = "facebook/musicgen-large"
    lyrics_model_path: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    whisper_size: str = "large-v3"

    # Inference
    device: str = "cuda"
    max_audio_files: int = 10
    max_audio_duration_per_file: float = 180.0  # 3 minutes
    max_output_duration: float = 480.0           # 8 minutes
    min_output_duration: float = 30.0

    # API
    cors_origins: list[str] = ["*"]
    max_upload_size_mb: int = 100

    model_config = {"env_prefix": "GAC_", "case_sensitive": False}


settings = Settings()
