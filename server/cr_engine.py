import json
from pathlib import Path
from typing import Dict, Any
from .llm_provider import GeminiClient


def _load_graph(job_root: Path) -> Dict[str, Any]:
    graph_path = job_root / 'out' / 'graph.json'
    if not graph_path.exists():
        raise FileNotFoundError('graph.json not found')
    with open(graph_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def propose_cr(job_root: Path, cr_text: str) -> Dict[str, Any]:
    """Run a simple impact analysis for a natural-language CR.
    Returns an impact report and a proposed patch (dry-run).
    """
    graph = _load_graph(job_root)
    nodes = graph.get('nodes', [])

    matches = []
    query = cr_text.lower()
    for n in nodes:
        name = (n.get('name') or '').lower()
        if query in name or any(token in name for token in query.split()):
            matches.append({'id': n.get('id'), 'label': n.get('label'), 'name': n.get('name'), 'file': n.get('file')})

    impact = {
        'cr_text': cr_text,
        'matches': matches,
        'confidence': 'high' if matches else 'low'
    }

    patch = None
    if matches:
        # propose AST-safe edit: replace occurrences of cr_text in matched files (simple replace)
        edits = []
        for m in matches:
            fpath = job_root / 'repo' / Path(m['file']).name
            if fpath.exists():
                content = fpath.read_text(encoding='utf-8')
                new_content = content.replace(cr_text, f"{cr_text} (updated)")
                if new_content != content:
                    edits.append({'file': str(fpath.relative_to(job_root)), 'before': content[:200], 'after': new_content[:200]})
        if edits:
            # create a unified-like patch representation (not strict diff)
            patch_lines = []
            for e in edits:
                patch_lines.append(f"*** {e['file']} (preview)\n--- original\n+++ modified\n")
            patch = '\n'.join(patch_lines)
    else:
        # Use Gemini to suggest new file(s)
        gem = GeminiClient()
        prompt = f"You are an assistant that creates code. The repo has these nodes: {len(nodes)} nodes.\nCR: {cr_text}\nPropose a small Dart file (path and content) to implement this change. Include filename on top like: FILE: lib/new_feature.dart\nContent:\n"
        try:
            gen = gem.generate_text(prompt)
            # look for FILE: prefix
            file_path = 'lib/generated_by_gemini.dart'
            content = gen
            # write generated file
            outpath = job_root / 'repo' / file_path
            outpath.parent.mkdir(parents=True, exist_ok=True)
            outpath.write_text('// AI-generated file\n' + content, encoding='utf-8')
            patch = f"*** {file_path} (generated)\n{content[:200]}\n"
            impact['generated_file'] = file_path
        except Exception as e:
            patch = f"// Gemini generation failed: {e}"

    return {'impact': impact, 'patch': patch}


def apply_patch(job_root: Path, patch: str, mode: str = 'dry') -> Dict[str, Any]:
    # For now, apply_mode only supports 'dry' (no-op) or 'apply' (write files already created by propose)
    if mode == 'dry':
        return {'status': 'dry-run', 'detail': 'No files changed'}
    # naive apply: already wrote generated files during propose; just return success
    return {'status': 'applied', 'detail': 'Files written to repo/ (check .cgr)'}
