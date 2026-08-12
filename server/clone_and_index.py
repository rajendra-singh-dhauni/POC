import subprocess
import shutil
from pathlib import Path
import os
import json

from src.cgr_lite_cli import tree_parser, graph_builder


def clone_and_index_repo(repo_url: str, branch: str | None, token: str | None, job_id: str, work_root: Path) -> Path:
    """Clone the repo and run the existing indexer (Dart parser). Returns work dir path."""
    repo_dir = work_root / job_id / 'repo'
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    clone_url = repo_url
    if token and repo_url.startswith('https://'):
        clone_url = repo_url.replace('https://', f'https://{token}@')

    subprocess.check_call(['git', 'clone', '--depth', '1', clone_url, str(repo_dir)])
    if branch:
        subprocess.check_call(['git', 'checkout', branch], cwd=str(repo_dir))

    # Build grammar and parse
    parser = tree_parser.DartTreeParser()
    parser.ensure_grammar_built()

    files = list(repo_dir.rglob('*.dart'))
    builder = graph_builder.GraphBuilder(project_name=repo_dir.name)

    for fp in files:
        root, lang = parser.parse_file(fp)
        funcs = parser.extract_functions(root, fp)
        classes = parser.extract_classes(root, fp)
        calls = parser.extract_calls(root, fp)
        imports = parser.extract_imports(fp)

        builder.add_module(fp)
        for c in classes:
            builder.add_class(fp, c)
        for f in funcs:
            builder.add_function(fp, f)
        for imp in imports:
            builder.add_import(fp, imp)
        for call in calls:
            builder.add_call(fp, call)

    builder.resolve_calls()

    out_dir = work_root / job_id / 'out'
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / 'graph.json', 'w', encoding='utf-8') as f:
        json.dump(builder.to_dict(), f, indent=2)

    with open(out_dir / 'graph.cypher', 'w', encoding='utf-8') as f:
        f.write(builder.to_cypher())

    return work_root / job_id
