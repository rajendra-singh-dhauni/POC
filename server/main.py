from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid
import os
from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .clone_and_index import clone_and_index_repo
from .llm_provider import GeminiClient

APP_DIR = Path(__file__).resolve().parent
WORK_DIR = APP_DIR.parent / '.cgr' / 'repos'
WORK_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="CGR Lite - Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs = {}

class SubmitRepo(BaseModel):
    repo_url: str
    branch: str | None = None
    token: str | None = None


@app.post("/api/submit-repo")
def submit_repo(payload: SubmitRepo, background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "logs": []}

    # run clone & index in background
    background_tasks.add_task(_run_index, job_id, payload.repo_url, payload.branch, payload.token)
    return {"job_id": job_id}


@app.get("/api/job-status/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/artifact/{job_id}/{path:path}")
def get_artifact(job_id: str, path: str):
    base = WORK_DIR / job_id / 'out'
    p = base / path
    if not p.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(p)


def _append_log(job_id: str, msg: str):
    jobs[job_id]["logs"].append(msg)


def _run_index(job_id: str, repo_url: str, branch: str | None, token: str | None):
    try:
        jobs[job_id]["status"] = "cloning"
        _append_log(job_id, f"Cloning {repo_url} ...")
        dest = clone_and_index_repo(repo_url, branch, token, job_id, work_root=WORK_DIR)
        jobs[job_id]["status"] = "parsing"
        _append_log(job_id, f"Index created at {dest}")
        jobs[job_id]["status"] = "done"
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        _append_log(job_id, f"Error: {e}")
        return
