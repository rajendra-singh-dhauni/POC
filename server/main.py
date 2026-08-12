from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid
import os
from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .clone_and_index import clone_and_index_repo
from .llm_provider import GeminiClient
from .docgen_api import generate_docs_for_job
from .cr_engine import propose_cr, apply_patch

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

class ProposeCRPayload(BaseModel):
    job_id: str
    cr_text: str

class ApplyCRPayload(BaseModel):
    job_id: str
    patch: str | None = None
    mode: str | None = 'dry'


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


@app.post("/api/propose-cr")
def api_propose_cr(payload: ProposeCRPayload):
    job_id = payload.job_id
    cr_text = payload.cr_text
    job_root = WORK_DIR / job_id
    if not job_root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        result = propose_cr(job_root, cr_text)
        # append to job logs
        jobs.setdefault(job_id, {"status":"unknown","logs":[]})
        jobs[job_id]["logs"].append(f"propose-cr: {cr_text}")
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/apply-cr")
def api_apply_cr(payload: ApplyCRPayload):
    job_id = payload.job_id
    patch = payload.patch
    mode = payload.mode or 'dry'
    job_root = WORK_DIR / job_id
    if not job_root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        res = apply_patch(job_root, patch or '', mode=mode)
        jobs.setdefault(job_id, {"status":"unknown","logs":[]})
        jobs[job_id]["logs"].append(f"apply-cr: mode={mode}")
        return JSONResponse(res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _append_log(job_id: str, msg: str):
    jobs[job_id]["logs"].append(msg)


def _run_index(job_id: str, repo_url: str, branch: str | None, token: str | None):
    try:
        jobs[job_id]["status"] = "cloning"
        _append_log(job_id, f"Cloning {repo_url} ...")
        dest = clone_and_index_repo(repo_url, branch, token, job_id, work_root=WORK_DIR)
        jobs[job_id]["status"] = "parsing"
        _append_log(job_id, f"Index created at {dest}")

        # generate docs automatically after indexing
        try:
            jobs[job_id]["status"] = "docgen"
            _append_log(job_id, "Generating SRS/TDD and diagrams...")
            job_root = WORK_DIR / job_id
            docs_dir = generate_docs_for_job(job_root)
            _append_log(job_id, f"Docs generated at {docs_dir}")
        except Exception as e:
            _append_log(job_id, f"Docgen failed: {e}")

        jobs[job_id]["status"] = "done"
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        _append_log(job_id, f"Error: {e}")
        return
