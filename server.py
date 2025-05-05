import os
import time
import json
import gzip
import threading
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

# === Logger ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReportServer")

# === FastAPI App ===
report_app = FastAPI()

# === Muistiin tallennetut raportit ===
stored_reports = {}
LOCK = threading.Lock()
ALLOWED_PREFIXES = ("scan-", "build-", "snapshot-", "test-", "recovery-")

# === Raportin skeema ===
class Report(BaseModel):
    task_id: str = Field(..., description="Unique identifier with required prefix")
    project_structure: dict
    validation_results: dict
    snapshot_metadata: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=lambda: time.time())

# === POST /report (gzip + JSON) ===
@report_app.post("/report")
async def receive_report(request: Request):
    try:
        if request.headers.get("Content-Encoding") == "gzip":
            compressed = await request.body()
            decompressed = gzip.decompress(compressed)
            data = json.loads(decompressed.decode("utf-8"))
        else:
            data = await request.json()

        report = Report(**data)

        if not any(report.task_id.startswith(p) for p in ALLOWED_PREFIXES):
            logger.warning(f"[✗] Invalid task_id prefix: {report.task_id}")
            raise HTTPException(status_code=400, detail="Invalid task_id prefix")

        with LOCK:
            stored_reports[report.task_id] = {
                "report": report.dict(),
                "timestamp": time.time()
            }

        logger.info(f"[✓] Report stored: {report.task_id}")
        return JSONResponse(status_code=200, content={"status": "stored", "task_id": report.task_id})

    except Exception as e:
        logger.error(f"[✗] Failed to parse report: {e}")
        raise HTTPException(status_code=400, detail="There was an error parsing the body")

# === GET /report/{task_id} ===
@report_app.get("/report/{task_id}")
async def get_report(task_id: str):
    with LOCK:
        data = stored_reports.get(task_id)
        if not data:
            logger.warning(f"[✗] Report not found: {task_id}")
            raise HTTPException(status_code=404, detail="Report not found")
        logger.info(f"[→] Report retrieved: {task_id}")
        return JSONResponse(status_code=200, content=data["report"])

# === GET /report/list?prefix=... ===
@report_app.get("/report/list")
async def list_reports(prefix: Optional[str] = None):
    with LOCK:
        all_ids = list(stored_reports.keys())
        if prefix:
            filtered = [tid for tid in all_ids if tid.startswith(prefix)]
            logger.info(f"[→] Listed {len(filtered)} reports with prefix '{prefix}'.")
            return {"reports": filtered}
        logger.info(f"[→] Listed all {len(all_ids)} reports.")
        return {"reports": all_ids}

# === GET /health ===
@report_app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "stored_reports": len(stored_reports),
        "valid_prefixes": ALLOWED_PREFIXES
    }

# === Automaattinen siivous säikeessä ===
def cleanup_reports(expiry_seconds=1800, cleanup_interval=60):
    while True:
        now = time.time()
        removed = 0
        with LOCK:
            expired = [tid for tid, val in stored_reports.items() if now - val["timestamp"] > expiry_seconds]
            for tid in expired:
                del stored_reports[tid]
                removed += 1
        if removed:
            logger.info(f"[⏳] Removed {removed} expired reports.")
        time.sleep(cleanup_interval)

threading.Thread(target=cleanup_reports, daemon=True).start()

# === SNAPSHOT storage ===
SNAPSHOT_DIR = "snapshot_storage"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# === POST /snapshot (upload binary .zip/.tar etc) ===
@report_app.post("/snapshot")
async def receive_snapshot(
    file: UploadFile = File(...),
    task_id: str = Form(...),
    agent_id: Optional[str] = Form(None),
    timestamp: Optional[float] = Form(default_factory=lambda: time.time())
):
    if not any(task_id.startswith(p) for p in ALLOWED_PREFIXES):
        logger.warning(f"[✗] Invalid snapshot task_id prefix: {task_id}")
        raise HTTPException(status_code=400, detail="Invalid task_id prefix")

    try:
        file_bytes = await file.read()
        filename = f"{task_id}.snapshot"
        full_path = os.path.join(SNAPSHOT_DIR, filename)

        with open(full_path, "wb") as f:
            f.write(file_bytes)

        logger.info(f"[📦] Snapshot stored: {filename} ({len(file_bytes)} bytes)")
        return {
            "status": "snapshot stored",
            "task_id": task_id,
            "agent_id": agent_id,
            "size_bytes": len(file_bytes),
            "timestamp": timestamp
        }

    except Exception as e:
        logger.error(f"[✗] Failed to store snapshot: {e}")
        raise HTTPException(status_code=500, detail="Snapshot storage failed")

# === GET /snapshot/{task_id} (verify existence) ===
@report_app.get("/snapshot/{task_id}")
async def check_snapshot_exists(task_id: str):
    path = os.path.join(SNAPSHOT_DIR, f"{task_id}.snapshot")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"exists": True, "task_id": task_id}

# === GET /snapshot/download/{task_id} (return binary) ===
@report_app.get("/snapshot/download/{task_id}")
async def download_snapshot(task_id: str):
    path = os.path.join(SNAPSHOT_DIR, f"{task_id}.snapshot")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    logger.info(f"[↓] Downloading snapshot: {task_id}")
    return FileResponse(path, media_type="application/octet-stream", filename=f"{task_id}.snapshot")