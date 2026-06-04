"""Runtime config API — reads/writes .env for user-facing settings."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import APIResponse

router = APIRouter(prefix="/config", tags=["config"])

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# Settings exposed to the frontend (not api_key for security)
PUBLIC_KEYS = [
    "EMBED_MODE",
    "EMBED_LOCAL_MODEL",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "TOP_K",
    "MIN_SCORE",
    "RERANK_TOP_K",
    "RECALL_TOP_K",
    "API_RETRY_TIMES",
]


def _read_env() -> dict[str, str]:
    """Parse .env into a dict, preserving comments."""
    result: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(\w+)\s*=\s*(.*)", line)
            if m:
                result[m.group(1)] = m.group(2).strip()
    return result


def _write_env_key(key: str, value: str) -> None:
    """Update a single key in the .env file, or append if not found."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    updated = False
    new_lines = []
    for line in lines:
        m = re.match(rf"^{key}\s*=", line.strip())
        if m:
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@router.get("", response_model=APIResponse)
async def get_config():
    """Return user-facing configuration values."""
    env = _read_env()
    result = {}
    for key in PUBLIC_KEYS:
        env_val = env.get(key)
        if env_val is not None:
            result[key.lower()] = env_val
        else:
            # Fall back to current runtime default
            attr = key.lower()
            default = getattr(settings, attr, None)
            result[key.lower()] = str(default) if default is not None else ""
    return APIResponse(data=result)


@router.post("", response_model=APIResponse)
async def update_config(body: dict):
    """Update configuration keys. Accepts a dict of uppercase keys.

    Example: {"EMBED_MODE": "api"}

    Note: changing EMBED_MODE requires server restart to take full effect
          because the vector dimension changes (512↔4096).
    """
    updated = {}
    # Keys that should be numeric
    NUM_KEYS = {"CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K", "MIN_SCORE", "RERANK_TOP_K", "RECALL_TOP_K", "API_RETRY_TIMES"}
    for key, value in body.items():
        key_upper = key.upper()
        if key_upper in PUBLIC_KEYS:
            str_value = str(value)
            _write_env_key(key_upper, str_value)
            # Update runtime settings object (coerce numeric types)
            attr = key_upper.lower()
            if hasattr(settings, attr):
                if key_upper in NUM_KEYS:
                    try:
                        setattr(settings, attr, float(str_value) if "." in str_value else int(str_value))
                    except ValueError:
                        setattr(settings, attr, str_value)
                else:
                    setattr(settings, attr, str_value)
            updated[key_upper] = str_value

    if not updated:
        return APIResponse(code=400, message="No valid config keys provided")

    return APIResponse(
        message="Config updated. Note: EMBED_MODE changes need server restart.",
        data=updated,
    )
