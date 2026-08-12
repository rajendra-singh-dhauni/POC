import json
from pathlib import Path
from .llm_provider import GeminiClient


def generate_docs_for_job(job_root: Path) -> Path:
    """Generate SRS.md, TDD.md and PlantUML files into job_root/out/docs using Gemini for prose.
    Returns the docs directory path.
    """
    out_dir = job_root / 'out'
    docs_dir = out_dir / 'docs'
    docs_dir.mkdir(parents=True, exist_ok=True)

    graph_path = out_dir / 'graph.json'
    if not graph_path.exists():
        raise FileNotFoundError('graph.json not found for job')

    with open(graph_path, 'r', encoding='utf-8') as f:
        graph = json.load(f)

    # basic summaries
    nodes = graph.get('nodes', [])
    edges = graph.get('edges', [])

    summary = f"Repository Knowledge Graph Summary\nNodes: {len(nodes)}\nEdges: {len(edges)}\n\nSample nodes:\n"
    for n in nodes[:10]:
        summary += f"- {n.get('label')} {n.get('name')} (file={n.get('file')})\n"

    # Use Gemini to expand into SRS and TDD
    gem = GeminiClient()

    srs_prompt = (
        "You are a software engineer. Given the following knowledge graph summary, write a concise SRS (functional and non-functional requirements) and acceptance criteria.\n\n" + summary
    )
    try:
        srs_text = gem.generate_text(srs_prompt)
    except Exception as e:
        srs_text = """# SRS (auto-generated)

Failed to generate SRS via Gemini: %s

Please inspect graph.json for details.""" % str(e)

    srs_path = docs_dir / 'SRS.md'
    with open(srs_path, 'w', encoding='utf-8') as f:
        f.write(srs_text)

    tdd_prompt = (
        "You are a system architect. Given the following knowledge graph summary, write a Technical Design Document describing architecture, major modules, data flows, and sequence outlines.\n\n" + summary
    )
    try:
        tdd_text = gem.generate_text(tdd_prompt)
    except Exception as e:
        tdd_text = """# TDD (auto-generated)

Failed to generate TDD via Gemini: %s

Please inspect graph.json for details.""" % str(e)

    tdd_path = docs_dir / 'TDD.md'
    with open(tdd_path, 'w', encoding='utf-8') as f:
        f.write(tdd_text)

    # Create a simple PlantUML module diagram placeholder
    puml = "@startuml\npackage Modules {\n"
    mod_names = set()
    for n in nodes:
        if n.get('label') == 'Module' and n.get('name'):
            mod_names.add(n.get('name'))
    for m in list(mod_names)[:20]:
        puml += f"  class {m}\n"
    puml += "}\n@enduml\n"
    puml_path = docs_dir / 'modules.puml'
    with open(puml_path, 'w', encoding='utf-8') as f:
        f.write(puml)

    # manifest linking (simple)
    manifest = {
        'nodes_count': len(nodes),
        'edges_count': len(edges),
        'srs': str(srs_path.name),
        'tdd': str(tdd_path.name),
        'diagrams': [str(puml_path.name)],
    }
    with open(docs_dir / 'manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    return docs_dir
