import json
from pathlib import Path
import click

from .tree_parser import DartTreeParser
from .graph_builder import GraphBuilder
from rich.progress import track
from rich import print


@click.group()
def cli():
    """cgr-lite CLI"""


@cli.command()
@click.option("--path", required=True, type=click.Path(exists=True), help="Path to local codebase to index")
@click.option("--output", default="out/graph.json", help="Output JSON path")
@click.option("--cypher", default="out/graph.cypher", help="Output Cypher path (optional)")
def index(path: str, output: str, cypher: str):
    """Index the Dart codebase at PATH and write the knowledge graph to OUTPUT (JSON)."""
    repo = Path(path)
    out_dir = Path(output).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    parser = DartTreeParser()
    parser.ensure_grammar_built()

    files = list(repo.rglob("*.dart"))
    if not files:
        print(f"[yellow]No .dart files found under {repo}. Nothing to do.[/yellow]")
        return

    builder = GraphBuilder(project_name=repo.name)

    for fp in track(files, description="Parsing files"):
        try:
            root, language = parser.parse_file(fp)
        except Exception as e:
            print(f"[red]Failed to parse {fp}: {e}[/red]")
            continue
        # extract facts and add to graph
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

    # resolve simple-name callees to function qns
    builder.resolve_calls()

    # export
    j = builder.to_dict()
    with open(output, "w", encoding="utf-8") as f:
        json.dump(j, f, indent=2)
    print(f"[green]Wrote JSON graph to {output}[/green]")

    if cypher:
        c = builder.to_cypher()
        with open(cypher, "w", encoding="utf-8") as f:
            f.write(c)
        print(f"[green]Wrote Cypher to {cypher}[/green]")
