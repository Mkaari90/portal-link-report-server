from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import threading
import time
import logging

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReportServer")

# FastAPI-sovellus
report_app = FastAPI()

# Raporttivarasto ja lukko
stored_reports = {}
LOCK = threading.Lock()

# Sallitut etuliitteet
ALLOWED_PREFIXES = ("scan-", "build-", "snapshot-", "test-", "recovery-")

# Raportin malli
class Report(BaseModel):
    task_id: str = Field(..., description="Unique identifier with required prefix")
    project_structure: dict
    validation_results: dict
    snapshot_metadata: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=lambda: time.time())

# POST /report
@report_app.post("/report")
async def receive_report(report: Report):
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

# GET /report/{task_id}
@report_app.get("/report/{task_id}")
async def get_report(task_id: str):
    with LOCK:
        data = stored_reports.get(task_id)
        if not data:
            logger.warning(f"[✗] Report not found: {task_id}")
            raise HTTPException(status_code=404, detail="Report not found")
        logger.info(f"[→] Report retrieved: {task_id}")
        return JSONResponse(status_code=200, content=data["report"])

# GET /report/list?prefix=...
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

# GET /health
@report_app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "stored_reports": len(stored_reports),
        "valid_prefixes": ALLOWED_PREFIXES
    }

# Puhdistus (TTL)
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

# Käynnistä siivoussäie
threading.Thread(target=cleanup_reports, daemon=True).start()