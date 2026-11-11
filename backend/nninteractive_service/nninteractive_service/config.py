from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


# Directory that holds the .env file and the on-disk model/data folders.
# Relative paths in config are resolved against this so the service works no
# matter what working directory uvicorn is launched from.
_SERVICE_DIR = Path(__file__).resolve().parent.parent


def _resolve_path(value: str | None) -> str | None:
    """Resolve a possibly-relative config path to an absolute one.

    Relative paths are anchored at the service directory (where .env lives),
    NOT the process working directory. nnInteractive looks up model metadata
    via os.path.isfile, so a relative model_dir silently breaks when the server
    is launched from a different CWD (FileNotFoundError on inference_info.json).
    """
    if not value:
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _SERVICE_DIR / path
    return str(path)


def _load_dotenv(env_path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Only sets variables that are NOT already present in the real environment,
    so real env vars always win over the file (env > .env > defaults).

    Zero-dependency: no python-dotenv. Minimal parsing — strips comments and
    surrounding quotes, skips blank/malformed lines.
    """
    path = env_path or _SERVICE_DIR / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.isidentifier() and not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        # strip a single layer of matching surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_prefix: str = "/api/v1"
    data_dir: Path = Path(_resolve_path(os.environ.get("NNINTERACTIVE_BACKEND_DATA_DIR", "/workspace/data/nninteractive_backend")))
    engine: str = os.environ.get("NNINTERACTIVE_BACKEND_ENGINE", "mock")
    mock_default_shape_zyx: tuple[int, int, int] = (64, 128, 128)
    session_ttl_seconds: int = int(os.environ.get("NNINTERACTIVE_BACKEND_SESSION_TTL", "3600"))
    local_model_dir: str | None = _resolve_path(os.environ.get("NNINTERACTIVE_BACKEND_LOCAL_MODEL_DIR"))
    local_device: str = os.environ.get("NNINTERACTIVE_BACKEND_LOCAL_DEVICE", "cuda")
    remote_server_url: str | None = os.environ.get("NNINTERACTIVE_BACKEND_REMOTE_URL")
    remote_api_key: str | None = os.environ.get("NNINTERACTIVE_BACKEND_REMOTE_API_KEY")


settings = Settings()
