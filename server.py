from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import threading
import time
import uuid

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
    snapshot_metadata: dict = Field(..., description="Optional snapshot info", default={})
    timestamp: float = Field(default_factory=lambda: time.time(), description="Time of report creation")

# Vastaanota raportti
@report_app.post("/report")
async def receive_report(report: Report):
    with LOCK:
        stored_reports[report.task_id] = {
            "report": report.dict(),
            "timestamp": time.time()
        }
    return JSONResponse(status_code=200, content={"status": "Report received", "id": report.task_id})

# Hae raportti ID:n perusteella
@report_app.get("/report/{report_id}")
async def get_report(report_id: str):
    with LOCK:
        report_data = stored_reports.get(report_id)
        if not report_data:
            raise HTTPException(status_code=404, detail="Report not found")
        return JSONResponse(status_code=200, content=report_data["report"])

# Poistetaan vanhat raportit (esim. yli 30 min vanhat)
def cleanup_reports():
    while True:
        current_time = time.time()
        with LOCK:
            to_delete = [key for key, value in stored_reports.items() if current_time - value["timestamp"] > 1800]
            for key in to_delete:
                del stored_reports[key]
        time.sleep(60)

# Siivouskäynnistys erillisessä säikeessä
threading.Thread(target=cleanup_reports, daemon=True).start()

# Terveyden tarkistus
@report_app.get("/health")
async def health_check():
    return {"status": "ok", "stored_reports": len(stored_reports)}
