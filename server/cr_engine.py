import json
from pathlib import Path
from typing import Dict, Any
from .llm_provider import GeminiClient
import difflib
import subprocess
import os


def _load_graph(job_root: Path) -> Dict[str, Any]:
    graph_path = job_root / 'out' / 'graph.json'
    if not graph_path.exists():
        raise FileNotFoundError('graph.json not found')
    with open(graph_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _semantic_matches(nodes, query, top_n=10, cutoff=0.6):
    """Simple semantic-like matching using difflib on node names and token overlap."""
    names = [ (n.get('id'), (n.get('name') or ''), n) for n in nodes ]
    candidates = []
    q = query.lower()
    for nid, name, node in names:
        name_l = (name or '').lower()
        # ratio by difflib
        ratio = difflib.SequenceMatcher(None, q, name_l).ratio()
        # token overlap
        qtokens = set(q.split())
        ntokens = set(name_l.split())
        overlap = 0.0
        if qtokens:
            overlap = len(qtokens & ntokens) / len(qtokens)
        score = max(ratio, overlap)
        if score >= cutoff:
            candidates.append( (score, node) )
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [c[1] for c in candidates[:top_n]]


def propose_cr(job_root: Path, cr_text: str) -> Dict[str, Any]:
    """Run an impact analysis for a natural-language CR.
    Returns an impact report and a proposed patch (dry-run).
    Uses simple semantic matching and token heuristics; falls back to Gemini for generation.
    """
    graph = _load_graph(job_root)
    nodes = graph.get('nodes', [])

    matches = []
    # semantic matching
    sem_matches = _semantic_matches(nodes, cr_text, top_n=20, cutoff=0.4)
    for n in sem_matches:
        matches.append({'id': n.get('id'), 'label': n.get('label'), 'name': n.get('name'), 'file': n.get('file')})

    # exact token based matching as well
    q = cr_text.lower()
    for n in nodes:
        name = (n.get('name') or '').lower()
        if any(token in name for token in q.split()):
            if not any(m['id'] == n.get('id') for m in matches):
                matches.append({'id': n.get('id'), 'label': n.get('label'), 'name': n.get('name'), 'file': n.get('file')})

    impact = {
        'cr_text': cr_text,
        'matches': matches,
        'confidence': 'high' if matches else 'low'
    }

    patch = None
    generated_file = None
    if matches:
        # propose edits: find files and produce a preview of replacement
        edits = []
        for m in matches:
            if not m.get('file'):
                continue
            # try to find file under repo by suffix match
            repo_files = list((job_root / 'repo').rglob(Path(m['file']).name))
            if not repo_files:
                continue
            fpath = repo_files[0]
            try:
                content = fpath.read_text(encoding='utf-8')
            except Exception:
                continue
            # naive replacement: if cr_text appears, propose replacement; else show context and insertion suggestion
            if cr_text in content:
                new_content = content.replace(cr_text, f"{cr_text} (updated)")
                edits.append({'file': str(fpath.relative_to(job_root)), 'before': content[:400], 'after': new_content[:400]})
            else:
                # show suggestion to modify function/class name occurrences
                edits.append({'file': str(fpath.relative_to(job_root)), 'before': content[:400], 'after': f"// Suggestion: {cr_text}\n{content[:400]}"})
        if edits:
            patch_lines = []
            for e in edits:
                patch_lines.append(f"*** {e['file']} (preview)\n--- before\n+++ after\n{e['after']}\n")
            patch = '\n'.join(patch_lines)
    else:
        # Use Gemini to suggest new file(s)
        gem = GeminiClient()
        prompt = (
            f"You are an assistant that creates Dart code.\nCR: {cr_text}\n"
            "Propose a small Dart file to implement this change. Provide the path as 'FILE: lib/new_feature.dart' on the first line, followed by the file content. Keep it concise."
        )
        try:
            gen = gem.generate_text(prompt)
            # find FILE: prefix
            file_path = 'lib/generated_by_gemini.dart'
            lines = gen.splitlines()
            if lines and lines[0].strip().upper().startswith('FILE:'):
                fp = lines[0].split(':',1)[1].strip()
                if fp:
                    file_path = fp
                    content = '\n'.join(lines[1:])
                else:
                    content = '\n'.join(lines)
            else:
                content = gen
            outpath = job_root / 'repo' / file_path
            outpath.parent.mkdir(parents=True, exist_ok=True)
            outpath.write_text('// AI-generated file\n' + content, encoding='utf-8')
            patch = f"*** {file_path} (generated)\n{content[:800]}\n"
            generated_file = file_path
        except Exception as e:
            patch = f"// Gemini generation failed: {e}"

    return {'impact': impact, 'patch': patch, 'generated_file': generated_file}


def apply_patch(job_root: Path, patch: str, mode: str = 'dry', verify: bool = True) -> Dict[str, Any]:
    """Apply the patch. If mode='dry' do not persist. If mode='apply' write files and run optional format/analyze verification.
    Returns status dict.
    """
    # For Phase-1 we assume propose_cr already wrote generated files to repo when needed.
    if mode == 'dry':
        return {'status': 'dry-run', 'detail': 'No files changed'}

    # apply mode: attempt to run dart format and dart analyze if available
    repo_dir = job_root / 'repo'
    result = {'status': 'applied', 'issues': []}

    if verify:
        # run dart format
        try:
            subprocess.run(['dart', 'format', '.'], cwd=str(repo_dir), check=True, timeout=30)
            result['format'] = 'ok'
        except Exception as e:
            result['format'] = f'failed: {e}'
            result['issues'].append(str(e))
        # run dart analyze
        try:
            proc = subprocess.run(['dart', 'analyze'], cwd=str(repo_dir), capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                result['analyze'] = 'issues'
                result['analyze_output'] = proc.stdout + '\n' + proc.stderr
                result['issues'].append('dart analyze reported issues')
            else:
                result['analyze'] = 'ok'
        except Exception as e:
            result['analyze'] = f'failed: {e}'
            result['issues'].append(str(e))

    # final result
    if result['issues']:
        result['status'] = 'applied_with_issues'
    else:
        result['status'] = 'applied'

    return result
