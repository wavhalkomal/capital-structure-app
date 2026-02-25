from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .jobs import JobManager
from .market_cap import get_market_cap_mm_yfinance
from .settings import CORS_ALLOW_ORIGINS, MAX_UPLOAD_BYTES, STORAGE_DIR

PARSERS_DIR = Path(__file__).resolve().parents[1] / "parsers"

app = FastAPI(title="Capital Structure Extractor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS if CORS_ALLOW_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jm = JobManager(parsers_dir=PARSERS_DIR)


@app.get("/api/health")
def health():
    return {"ok": True}


def _save_upload(upload: UploadFile, dest: Path) -> None:
    """Save upload to disk with size cap enforcement."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with dest.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"Upload too large (>{MAX_UPLOAD_BYTES} bytes)")
            f.write(chunk)


@app.post("/api/jobs")
def create_job(
    balance_sheet: UploadFile = File(..., description="balance_sheet.json"),
    debt_note: UploadFile = File(..., description="debt_note.html"),
    lease_note: UploadFile = File(..., description="lease_note.html"),
    metadata: UploadFile = File(..., description="metadata.json"),
    ticker: Optional[str] = Form(None, description="Optional equity ticker to auto-fetch market cap (e.g., AAP)"),
    market_cap_mm: Optional[float] = Form(
        None, description="Optional override market cap in $mm. If provided, overrides ticker fetch."
    ),
    period_end_text: Optional[str] = Form(None, description="Optional period end text override"),
):
    job = jm.create_job()

    try:
        _save_upload(balance_sheet, job.input_dir / "balance_sheet.json")
        _save_upload(debt_note, job.input_dir / "debt_note.html")
        _save_upload(lease_note, job.input_dir / "lease_note.html")
        _save_upload(metadata, job.input_dir / "metadata.json")

        # quick validation: metadata must be json
        try:
            json.loads((job.input_dir / "metadata.json").read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="metadata.json is not valid JSON")

    except HTTPException:
        jm.delete_job_files(job.id)
        raise
    except Exception as e:
        jm.delete_job_files(job.id)
        raise HTTPException(status_code=500, detail=f"Failed saving uploads: {e}")

    # --------------------------------------------------
    # Resolve Market Cap (Manual Override > Ticker Fetch)
    # --------------------------------------------------
    resolved_market_cap_mm = market_cap_mm
    market_cap_meta = None

    if resolved_market_cap_mm is None and ticker:
        res = get_market_cap_mm_yfinance(ticker)
        if res is not None:
            resolved_market_cap_mm = float(res.market_cap_mm)
            market_cap_meta = {
                "source": res.source,
                "currency": res.currency,
                "as_of_utc": res.as_of_utc,
                "details": res.details,
            }
    if resolved_market_cap_mm is None:
        jm.delete_job_files(job.id)
        raise HTTPException(
            status_code=400,
            detail="Missing market_cap_mm. Provide market_cap_mm ($mm) or ticker to fetch it automatically.",
        )

    jm.start_job(
        job.id,
        market_cap_mm=resolved_market_cap_mm,
        period_end_text=period_end_text,
        ticker=ticker,
        market_cap_meta=market_cap_meta,
    )

    return {
        "job_id": job.id,
        "status": job.status,
        "market_cap_mm": resolved_market_cap_mm,
        "market_cap_meta": market_cap_meta,
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "error": job.error,
        "ticker": job.ticker,
        "market_cap_mm": job.market_cap_mm,
        "market_cap_meta": job.market_cap_meta,
    }


@app.get("/api/jobs/{job_id}/result")
def get_result(job_id: str):
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == "failed":
        raise HTTPException(status_code=400, detail=job.error or "job failed")
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail=f"job not ready (status={job.status})")

    try:
        return JSONResponse(jm.read_result(job_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/{job_id}/download/html")
def download_html(job_id: str):
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "succeeded" or not job.html_path or not job.html_path.exists():
        raise HTTPException(status_code=409, detail="html not available")
    return FileResponse(path=str(job.html_path), filename=f"{job_id}.html", media_type="text/html")


@app.get("/api/jobs/{job_id}/download/json")
def download_json(job_id: str):
    job = jm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != "succeeded" or not job.built_json_path or not job.built_json_path.exists():
        raise HTTPException(status_code=409, detail="json not available")
    return FileResponse(path=str(job.built_json_path), filename=f"{job_id}.json", media_type="application/json")


# ===============================
# Serve React Frontend (Production)
# ===============================

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from fastapi import HTTPException

# # Path to frontend/dist
# FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# if FRONTEND_DIST.exists():

#     # Serve static assets (JS/CSS)
#     app.mount(
#         "/assets",
#         StaticFiles(directory=str(FRONTEND_DIST / "assets")),
#         name="assets",
#     )

#     # SPA fallback — serve index.html for all non-API routes
#     @app.get("/{full_path:path}")
#     async def serve_spa(full_path: str):
#         # Don't override API routes
#         if full_path.startswith("api/"):
#             raise HTTPException(status_code=404, detail="Not Found")

#         index_file = FRONTEND_DIST / "index.html"
#         return FileResponse(str(index_file))

# ---- Serve Vite frontend ----
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # Serve static assets
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def frontend_root():
        return FileResponse(FRONTEND_DIST / "index.html")

    # SPA fallback (so refresh on /some/page works)
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Don’t hijack API/docs paths
        if full_path.startswith(("api", "docs", "openapi.json")):
            raise HTTPException(status_code=404, detail="Not Found")

        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        return FileResponse(FRONTEND_DIST / "index.html")
        

# Ensure storage dir exists
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

