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
    procedure_steps: list[str] = []


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
        # Stream the graph so we can push procedure_steps to the job store
        # as soon as Node 1 finishes (while Node 2 is still running).
        final_state = initial_state
        for update in chemistry_graph.stream(initial_state):
            # Each update is {node_name: partial_state_dict}
            for _node_name, partial in update.items():
                final_state = {**final_state, **partial}

            # If procedure_steps just became available, push them to the job
            steps = final_state.get("procedure_steps", [])
            if steps:
                with _jobs_lock:
                    _jobs[job_id] = StatusResponse(
                        status=JobStatus.PROCESSING,
                        procedure_steps=steps,
                    )

        if final_state.get("error"):
            logger.error("Job %s failed (agent error): %s", job_id, final_state["error"])
            result = StatusResponse(
                status=JobStatus.FAILED,
                error_message=final_state["error"],
                procedure_steps=final_state.get("procedure_steps", []),
            )
        else:
            logger.info("Job %s completed successfully — video_url: %s", job_id, final_state["video_url"])
            result = StatusResponse(
                status=JobStatus.COMPLETED,
                video_url=final_state["video_url"],
                procedure_steps=final_state.get("procedure_steps", []),
            )

    except Exception as exc:
        logger.error("Job %s failed (unhandled exception): %s", job_id, exc, exc_info=True)
        # Try to preserve any steps gathered before the failure
        steps = final_state.get("procedure_steps", []) if final_state else []
        result = StatusResponse(
            status=JobStatus.FAILED,
            error_message=str(exc),
            procedure_steps=steps,
        )

    with _jobs_lock:
        _jobs[job_id] = result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=False)
