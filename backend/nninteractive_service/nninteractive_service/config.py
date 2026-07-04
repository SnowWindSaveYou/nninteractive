from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_prefix: str = "/api/v1"
    data_dir: Path = Path(os.environ.get("NNINTERACTIVE_BACKEND_DATA_DIR", "/workspace/data/nninteractive_backend"))
    engine: str = os.environ.get("NNINTERACTIVE_BACKEND_ENGINE", "mock")
    mock_default_shape_zyx: tuple[int, int, int] = (64, 128, 128)
    session_ttl_seconds: int = int(os.environ.get("NNINTERACTIVE_BACKEND_SESSION_TTL", "3600"))
    local_model_dir: str | None = os.environ.get("NNINTERACTIVE_BACKEND_LOCAL_MODEL_DIR")
    local_device: str = os.environ.get("NNINTERACTIVE_BACKEND_LOCAL_DEVICE", "cuda")
    remote_server_url: str | None = os.environ.get("NNINTERACTIVE_BACKEND_REMOTE_URL")
    remote_api_key: str | None = os.environ.get("NNINTERACTIVE_BACKEND_REMOTE_API_KEY")


settings = Settings()
