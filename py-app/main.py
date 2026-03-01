from __future__ import annotations

import logging
import threading
import uuid
from enum import Enum
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()

from agent import chemistry_graph
from agent.state import ExperimentState


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    experiment_name: str


class GenerateResponse(BaseModel):
    job_id: str


class JobStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"


class StatusResponse(BaseModel):
    status: JobStatus
    video_url: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------

_jobs: dict[str, StatusResponse] = {}
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="ChemLab AI Agent", version="1.0.0")


@app.post("/generate", response_model=GenerateResponse, status_code=202)
def generate(request: GenerateRequest) -> GenerateResponse:
    job_id = str(uuid.uuid4())
    logger.info("Received generation request — experiment: '%s', job_id: %s",
                request.experiment_name, job_id)

    with _jobs_lock:
        _jobs[job_id] = StatusResponse(status=JobStatus.PENDING)

    threading.Thread(
        target=_run_agent,
        args=(job_id, request.experiment_name),
        daemon=True,
    ).start()

    return GenerateResponse(job_id=job_id)


@app.get("/status/{job_id}", response_model=StatusResponse)
def get_status(job_id: str) -> StatusResponse:
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return job


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_agent(job_id: str, experiment_name: str) -> None:
    logger.info("Starting agent pipeline — job_id: %s, experiment: '%s'", job_id, experiment_name)
    with _jobs_lock:
        _jobs[job_id] = StatusResponse(status=JobStatus.PROCESSING)

    initial_state: ExperimentState = {
        "experiment_name": experiment_name,
        "procedure_steps": [],
        "clip_s3_keys": [],
        "final_video_key": None,
        "video_url": None,
        "error": None,
    }

    try:
        final_state: ExperimentState = chemistry_graph.invoke(initial_state)

        if final_state.get("error"):
            logger.error("Job %s failed (agent error): %s", job_id, final_state["error"])
            result = StatusResponse(
                status=JobStatus.FAILED,
                error_message=final_state["error"],
            )
        else:
            logger.info("Job %s completed successfully — video_url: %s", job_id, final_state["video_url"])
            result = StatusResponse(
                status=JobStatus.COMPLETED,
                video_url=final_state["video_url"],
            )

    except Exception as exc:
        logger.error("Job %s failed (unhandled exception): %s", job_id, exc, exc_info=True)
        result = StatusResponse(
            status=JobStatus.FAILED,
            error_message=str(exc),
        )

    with _jobs_lock:
        _jobs[job_id] = result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=False)
