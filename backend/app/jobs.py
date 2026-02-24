# from __future__ import annotations
#
# import json
# import shutil
# import subprocess
# import threading
# import time
# import uuid
# from dataclasses import dataclass, field
# from pathlib import Path
# from typing import Any, Dict, Optional
#
# from .settings import MAX_CONCURRENT_JOBS, STORAGE_DIR
#
#
# @dataclass
# class Job:
#     id: str
#     status: str  # queued|running|succeeded|failed
#     created_at: float
#     updated_at: float
#     error: Optional[str] = None
#
#     # paths
#     job_dir: Path = field(default_factory=Path)
#     input_dir: Path = field(default_factory=Path)
#     output_dir: Path = field(default_factory=Path)
#
#     # artifacts
#     html_path: Optional[Path] = None
#     built_json_path: Optional[Path] = None
#
#
# class JobManager:
#     """Lightweight in-memory job manager with bounded concurrency.
#
#     For the challenge constraints (<=10 concurrent), this is reliable and simple.
#     Artifacts are persisted to disk so results remain available if the process
#     stays alive.
#     """
#
#     def __init__(self, parsers_dir: Path):
#         self.parsers_dir = parsers_dir
#         self._jobs: Dict[str, Job] = {}
#         self._lock = threading.Lock()
#         self._sema = threading.Semaphore(MAX_CONCURRENT_JOBS)
#
#     def create_job(self) -> Job:
#         job_id = uuid.uuid4().hex
#         now = time.time()
#
#         job_dir = STORAGE_DIR / job_id
#         input_dir = job_dir / "input"
#         output_dir = job_dir / "output"
#         input_dir.mkdir(parents=True, exist_ok=True)
#         output_dir.mkdir(parents=True, exist_ok=True)
#
#         job = Job(
#             id=job_id,
#             status="queued",
#             created_at=now,
#             updated_at=now,
#             job_dir=job_dir,
#             input_dir=input_dir,
#             output_dir=output_dir,
#         )
#         with self._lock:
#             self._jobs[job_id] = job
#         return job
#
#     def get_job(self, job_id: str) -> Optional[Job]:
#         with self._lock:
#             return self._jobs.get(job_id)
#
#     def delete_job_files(self, job_id: str) -> None:
#         job = self.get_job(job_id)
#         if not job:
#             return
#         try:
#             shutil.rmtree(job.job_dir, ignore_errors=True)
#         except Exception:
#             pass
#
#     def _set_status(self, job_id: str, status: str, error: Optional[str] = None) -> None:
#         with self._lock:
#             j = self._jobs.get(job_id)
#             if not j:
#                 return
#             j.status = status
#             j.updated_at = time.time()
#             j.error = error
#
#     def _run_pipeline(
#         self,
#         job_id: str,
#         market_cap_mm: float,
#         period_end_text: Optional[str] = None,
#     ) -> None:
#         """Run your existing CLI scripts as subprocesses.
#
#         This avoids assumptions about internal function names.
#         """
#
#         job = self.get_job(job_id)
#         if not job:
#             return
#
#         self._set_status(job_id, "running")
#
#         # Inputs are expected to exist
#         bal = job.input_dir / "balance_sheet.json"
#         debt = job.input_dir / "debt_note.html"
#         lease = job.input_dir / "lease_note.html"
#         meta = job.input_dir / "metadata.json"
#
#         built_json = job.output_dir / "built_capital_structure.json"
#         out_html = job.output_dir / "generated.html"
#
#         builder = self.parsers_dir / "capital_structure_builder.py"
#         renderer = self.parsers_dir / "html_renderer.py"
#
#         # Build command
#         cmd_build = [
#             "python",
#             str(builder),
#             "--balance",
#             str(bal),
#             "--debt",
#             str(debt),
#             "--lease",
#             str(lease),
#             "--metadata",
#             str(meta),
#             "--market-cap-mm",
#             str(market_cap_mm),
#             "--out",
#             str(built_json),
#         ]
#         if period_end_text:
#             cmd_build.extend(["--period-end", period_end_text])
#
#         # Render command
#         cmd_render = [
#             "python",
#             str(renderer),
#             str(built_json),
#             "--out",
#             str(out_html),
#         ]
#
#         # Execute with the parsers directory on PYTHONPATH so your scripts can import each other if needed.
#         env = dict(**{**dict(**__import__("os").environ)})
#         env["PYTHONPATH"] = str(self.parsers_dir) + (":" + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
#
#         try:
#             proc1 = subprocess.run(cmd_build, capture_output=True, text=True, env=env)
#             if proc1.returncode != 0:
#                 raise RuntimeError(
#                     "capital_structure_builder.py failed\n"
#                     f"STDOUT:\n{proc1.stdout}\n\nSTDERR:\n{proc1.stderr}"
#                 )
#
#             proc2 = subprocess.run(cmd_render, capture_output=True, text=True, env=env)
#             if proc2.returncode != 0:
#                 raise RuntimeError(
#                     "html_renderer.py failed\n"
#                     f"STDOUT:\n{proc2.stdout}\n\nSTDERR:\n{proc2.stderr}"
#                 )
#
#             # Save artifact paths
#             job.html_path = out_html
#             job.built_json_path = built_json
#             self._set_status(job_id, "succeeded")
#
#         except Exception as e:
#             self._set_status(job_id, "failed", error=str(e))
#
#     def start_job(
#         self,
#         job_id: str,
#         market_cap_mm: float,
#         period_end_text: Optional[str] = None,
#     ) -> None:
#         """Starts job in a background thread, respecting max concurrency."""
#
#         def runner() -> None:
#             with self._sema:
#                 self._run_pipeline(job_id=job_id, market_cap_mm=market_cap_mm, period_end_text=period_end_text)
#
#         t = threading.Thread(target=runner, daemon=True)
#         t.start()
#
#     def read_result(self, job_id: str) -> Dict[str, Any]:
#         job = self.get_job(job_id)
#         if not job:
#             raise KeyError("job not found")
#         if job.status != "succeeded":
#             raise RuntimeError(f"job not succeeded (status={job.status})")
#
#         html = job.html_path.read_text(encoding="utf-8") if job.html_path and job.html_path.exists() else ""
#         built = {}
#         if job.built_json_path and job.built_json_path.exists():
#             built = json.loads(job.built_json_path.read_text(encoding="utf-8"))
#         return {"job_id": job.id, "html": html, "built": built}



from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .settings import MAX_CONCURRENT_JOBS, STORAGE_DIR


@dataclass
class Job:
    id: str
    status: str  # queued|running|succeeded|failed
    created_at: float
    updated_at: float
    error: Optional[str] = None

    # inputs/meta
    ticker: Optional[str] = None
    market_cap_mm: Optional[float] = None
    market_cap_meta: Optional[dict] = None

    # paths
    job_dir: Path = field(default_factory=Path)
    input_dir: Path = field(default_factory=Path)
    output_dir: Path = field(default_factory=Path)

    # artifacts
    html_path: Optional[Path] = None
    built_json_path: Optional[Path] = None


class JobManager:
    """Lightweight in-memory job manager with bounded concurrency."""

    def __init__(self, parsers_dir: Path):
        self.parsers_dir = parsers_dir
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._sema = threading.Semaphore(MAX_CONCURRENT_JOBS)

    def create_job(self) -> Job:
        job_id = uuid.uuid4().hex
        now = time.time()

        job_dir = STORAGE_DIR / job_id
        input_dir = job_dir / "input"
        output_dir = job_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        job = Job(
            id=job_id,
            status="queued",
            created_at=now,
            updated_at=now,
            job_dir=job_dir,
            input_dir=input_dir,
            output_dir=output_dir,
        )

        with self._lock:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def delete_job_files(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        try:
            shutil.rmtree(job.job_dir, ignore_errors=True)
        except Exception:
            pass

    def _set_status(self, job_id: str, status: str, error: Optional[str] = None) -> None:
        with self._lock:
            j = self._jobs.get(job_id)
            if not j:
                return
            j.status = status
            j.updated_at = time.time()
            j.error = error

    def _run_pipeline(
        self,
        job_id: str,
        market_cap_mm: float,
        period_end_text: Optional[str] = None,
        ticker: Optional[str] = None,
        market_cap_meta: Optional[dict] = None,
    ) -> None:
        """Run your existing CLI scripts as subprocesses."""

        job = self.get_job(job_id)
        if not job:
            return

        # store inputs/meta on the job for API visibility
        job.market_cap_mm = market_cap_mm
        job.ticker = ticker
        job.market_cap_meta = market_cap_meta

        self._set_status(job_id, "running")

        bal = job.input_dir / "balance_sheet.json"
        debt = job.input_dir / "debt_note.html"
        lease = job.input_dir / "lease_note.html"
        meta = job.input_dir / "metadata.json"

        built_json = job.output_dir / "built_capital_structure.json"
        out_html = job.output_dir / "generated.html"

        builder = self.parsers_dir / "capital_structure_builder.py"
        renderer = self.parsers_dir / "html_renderer.py"

        # Use the same Python interpreter running the API (important for conda env)
        python_bin = sys.executable

        cmd_build = [
            python_bin,
            str(builder),
            "--balance",
            str(bal),
            "--debt",
            str(debt),
            "--lease",
            str(lease),
            "--metadata",
            str(meta),
            "--market-cap-mm",
            str(market_cap_mm),
            "--out",
            str(built_json),
        ]
        if period_end_text:
            cmd_build.extend(["--period-end", period_end_text])

        cmd_render = [
            python_bin,
            str(renderer),
            str(built_json),
            "--out",
            str(out_html),
        ]

        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.parsers_dir) + (
            ":" + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else ""
        )

        try:
            proc1 = subprocess.run(cmd_build, capture_output=True, text=True, env=env)
            if proc1.returncode != 0:
                raise RuntimeError(
                    "capital_structure_builder.py failed\n"
                    f"STDOUT:\n{proc1.stdout}\n\nSTDERR:\n{proc1.stderr}"
                )

            proc2 = subprocess.run(cmd_render, capture_output=True, text=True, env=env)
            if proc2.returncode != 0:
                raise RuntimeError(
                    "html_renderer.py failed\n"
                    f"STDOUT:\n{proc2.stdout}\n\nSTDERR:\n{proc2.stderr}"
                )

            job.html_path = out_html
            job.built_json_path = built_json

            # Optional: append market cap note to HTML for bonus-point visibility
            if market_cap_meta:
                try:
                    note = (
                        "\n<!-- Market Cap (auto-fetched) -->\n"
                        '<div style="margin-top:12px;font-size:12px;color:#555;">'
                        f"<b>Market Cap (auto-fetched):</b> {market_cap_mm:.3f} $mm<br/>"
                        f"<b>Source:</b> {market_cap_meta.get('source')} | "
                        f"<b>As of (UTC):</b> {market_cap_meta.get('as_of_utc')}"
                        "</div>\n"
                    )
                    html = out_html.read_text(encoding="utf-8")
                    out_html.write_text(html + note, encoding="utf-8")
                except Exception:
                    # Do not fail job if note append fails
                    pass

            self._set_status(job_id, "succeeded")

        except Exception as e:
            self._set_status(job_id, "failed", error=str(e))

    def start_job(
        self,
        job_id: str,
        market_cap_mm: float,
        period_end_text: Optional[str] = None,
        ticker: Optional[str] = None,
        market_cap_meta: Optional[dict] = None,
    ) -> None:
        """Starts job in a background thread, respecting max concurrency."""

        def runner() -> None:
            with self._sema:
                self._run_pipeline(
                    job_id=job_id,
                    market_cap_mm=market_cap_mm,
                    period_end_text=period_end_text,
                    ticker=ticker,
                    market_cap_meta=market_cap_meta,
                )

        t = threading.Thread(target=runner, daemon=True)
        t.start()

    def read_result(self, job_id: str) -> Dict[str, Any]:
        job = self.get_job(job_id)
        if not job:
            raise KeyError("job not found")
        if job.status != "succeeded":
            raise RuntimeError(f"job not succeeded (status={job.status})")

        html = job.html_path.read_text(encoding="utf-8") if job.html_path and job.html_path.exists() else ""
        built = {}
        if job.built_json_path and job.built_json_path.exists():
            built = json.loads(job.built_json_path.read_text(encoding="utf-8"))

        return {
            "job_id": job.id,
            "html": html,
            "built": built,
            "ticker": job.ticker,
            "market_cap_mm": job.market_cap_mm,
            "market_cap_meta": job.market_cap_meta,
        }

