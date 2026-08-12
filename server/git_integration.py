import subprocess
import os
from pathlib import Path
import requests
import json

GITHUB_API = 'https://api.github.com'


def create_branch_and_push(repo_path: Path, branch_name: str, commit_message: str = 'cgr-lite: apply changes') -> dict:
    """Create a branch from current HEAD, commit current changes, and push to origin.
    Requires GITHUB_TOKEN or that the repo was cloned with a token that allows push.
    Returns dict with branch and push outcome.
    """
    # Ensure git is available
    repo_path = Path(repo_path)
    try:
        # create branch
        subprocess.check_call(['git', 'checkout', '-b', branch_name], cwd=str(repo_path))
    except subprocess.CalledProcessError:
        # branch may already exist locally; try checkout
        subprocess.check_call(['git', 'checkout', branch_name], cwd=str(repo_path))
    # add, commit
    subprocess.check_call(['git', 'add', '.'], cwd=str(repo_path))
    subprocess.check_call(['git', 'commit', '-m', commit_message], cwd=str(repo_path))
    # push
    subprocess.check_call(['git', 'push', '--set-upstream', 'origin', branch_name], cwd=str(repo_path))
    return {'branch': branch_name, 'pushed': True}


def create_pull_request(owner: str, repo: str, head: str, base: str = 'main', title: str = '', body: str = '') -> dict:
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise RuntimeError('GITHUB_TOKEN not set; cannot create PR')
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls"
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github+json'}
    payload = {'title': title or f'cgr-lite: {head}', 'head': head, 'base': base, 'body': body, 'draft': True}
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200,201):
        try:
            return {'error': r.status_code, 'text': r.text}
        except Exception:
            return {'error': r.status_code}
    return r.json()
