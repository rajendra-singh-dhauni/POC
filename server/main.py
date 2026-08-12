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
from .git_integration import create_branch_and_push, create_pull_request

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
    verify: bool | None = True

class PRPayload(BaseModel):
    job_id: str
    branch_name: str
    pr_title: str | None = None
    pr_body: str | None = None


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
    verify = payload.verify if payload.verify is not None else True
    job_root = WORK_DIR / job_id
    if not job_root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        res = apply_patch(job_root, patch or '', mode=mode, verify=verify)
        jobs.setdefault(job_id, {"status":"unknown","logs":[]})
        jobs[job_id]["logs"].append(f"apply-cr: mode={mode} verify={verify}")
        return JSONResponse(res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/commit-pr")
def api_commit_pr(payload: PRPayload):
    job_id = payload.job_id
    branch_name = payload.branch_name
    title = payload.pr_title or f'cgr-lite: changes for {job_id}'
    body = payload.pr_body or ''
    job_root = WORK_DIR / job_id
    if not job_root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        # create branch, commit & push
        out = create_branch_and_push(job_root / 'repo', branch_name)
        # create PR via GitHub API (extract owner/repo from original remote)
        # We assume the repo was cloned from GitHub and remote origin points to https://github.com/owner/repo.git
        # Read remote URL
        import subprocess
        rem = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=str(job_root / 'repo')).decode('utf-8').strip()
        # normalize
        if rem.endswith('.git'):
            rem = rem[:-4]
        # handle https or git@ formats
        owner_repo = None
        if rem.startswith('https://github.com/'):
            owner_repo = rem[len('https://github.com/'):]
        elif rem.startswith('git@github.com:'):
            owner_repo = rem[len('git@github.com:'):]
        else:
            owner_repo = None
        if owner_repo:
            owner, repo = owner_repo.split('/')[:2]
            pr = create_pull_request(owner, repo, head=branch_name, title=title, body=body)
        else:
            pr = {'warning': 'could not determine owner/repo from remote origin; PR not created'}
        jobs.setdefault(job_id, {"status":"unknown","logs":[]})
        jobs[job_id]["logs"].append(f"commit-pr: branch={branch_name}")
        return JSONResponse({'push': out, 'pr': pr})
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
