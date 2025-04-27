from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import threading
import time
import logging

# Setup basic logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReportServer")

# Luo FastAPI app
report_app = FastAPI()

# Muistiin tallennetut raportit
stored_reports = {}
LOCK = threading.Lock()

# Raportin skeema
class Report(BaseModel):
    task_id: str = Field(..., description="Unique identifier for the task")
    project_structure: dict = Field(..., description="Full project structure including files and contents")
    validation_results: dict = Field(..., description="Codebase validation results")
    snapshot_metadata: dict = Field(default_factory=dict, description="Optional snapshot info")
    timestamp: float = Field(default_factory=lambda: time.time(), description="Time of report creation")

# Vastaanota raportti
@report_app.post("/report")
async def receive_report(report: Report):
    with LOCK:
        stored_reports[report.task_id] = {
            "report": report.dict(),
            "timestamp": time.time()
        }
    logger.info(f"Report received: {report.task_id}")
    return JSONResponse(status_code=200, content={"status": "Report received", "id": report.task_id})

# Hae raportti ID:n perusteella
@report_app.get("/report/{report_id}")
async def get_report(report_id: str):
    with LOCK:
        report_data = stored_reports.get(report_id)
        if not report_data:
            logger.warning(f"Report not found: {report_id}")
            raise HTTPException(status_code=404, detail="Report not found")
        logger.info(f"Report retrieved: {report_id}")
        return JSONResponse(status_code=200, content=report_data["report"])

# Terveyden tarkistus
@report_app.get("/health")
async def health_check():
    return {"status": "ok", "stored_reports": len(stored_reports)}

# Poistetaan vanhat raportit automaattisesti
def cleanup_reports(expiry_seconds=1800, cleanup_interval=60):
    while True:
        current_time = time.time()
        deleted_count = 0
        with LOCK:
            to_delete = [key for key, value in stored_reports.items()
                         if current_time - value["timestamp"] > expiry_seconds]
            for key in to_delete:
                del stored_reports[key]
                deleted_count += 1
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired reports.")
        time.sleep(cleanup_interval)

# Käynnistä siivous säikeessä
threading.Thread(target=cleanup_reports, daemon=True).start()