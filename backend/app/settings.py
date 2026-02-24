from __future__ import annotations

import os
from pathlib import Path


def _env(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v not in (None, "") else default


APP_ENV = _env("APP_ENV", "dev")

# Comma-separated list of allowed origins for CORS (e.g. "http://localhost:5173,https://myapp.vercel.app")
CORS_ALLOW_ORIGINS = [o.strip() for o in _env("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()]

# Where uploaded inputs + outputs are stored per job
STORAGE_DIR = Path(_env("STORAGE_DIR", str(Path(__file__).resolve().parents[1] / "storage"))).resolve()

# Concurrency for parsing/rendering jobs
MAX_CONCURRENT_JOBS = int(_env("MAX_CONCURRENT_JOBS", "10"))

# Limit upload sizes (in bytes). FastAPI/Uvicorn also has its own limits; this is an app-level sanity check.
MAX_UPLOAD_BYTES = int(_env("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))  # 50MB
