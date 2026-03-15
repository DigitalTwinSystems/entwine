"""entwine CLI — entry point for the entwine command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
import uvicorn
from pydantic import ValidationError

import entwine
from entwine.config.loader import load_config

app = typer.Typer(
    name="entwine",
    help="LLM-powered enterprise digital twin simulation.",
    no_args_is_help=True,
)

_DEFAULT_CONFIG = Path("entwine.yaml")


@app.command()
def start(
    config: Path = typer.Option(
        _DEFAULT_CONFIG,
        "--config",
        "-c",
        help="Path to simulation config file (.yaml / .toml).",
        show_default=True,
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host address for the FastAPI server.",
        show_default=True,
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="TCP port for the FastAPI server.",
        show_default=True,
    ),
) -> None:
    """Load config, create the simulation engine, and start the FastAPI server."""
    try:
        cfg = load_config(config)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (ValueError, ValidationError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    agent_count = len(cfg.agents)

    # Create LLM router (reads API keys from env).
    from entwine.llm.router import LLMRouter
    from entwine.llm.settings import LLMSettings
    from entwine.simulation.engine import SimulationEngine
    from entwine.web.app import set_engine

    llm_settings = LLMSettings()
    llm_router = LLMRouter(settings=llm_settings)

    engine = SimulationEngine(cfg, llm_router=llm_router)
    set_engine(engine)

    typer.echo(
        f"Starting entwine — simulation: {cfg.simulation.name!r}, "
        f"agents: {agent_count}, "
        f"LLM: {llm_settings.standard_model}, "
        f"server: http://{host}:{port}"
    )

    uvicorn.run("entwine.web:app", host=host, port=port)


@app.command()
def validate(
    config: Path = typer.Option(
        _DEFAULT_CONFIG,
        "--config",
        "-c",
        help="Path to simulation config file (.yaml / .toml).",
        show_default=True,
    ),
) -> None:
    """Load and validate config, then print a summary."""
    try:
        cfg = load_config(config)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (ValueError, ValidationError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Config: {config}")
    typer.echo(f"Simulation: {cfg.simulation.name}")
    typer.echo(f"Enterprise: {cfg.enterprise.name}")
    typer.echo(f"Departments: {len(cfg.enterprise.departments)}")
    typer.echo(f"Agents: {len(cfg.agents)}")
    typer.echo("Config is valid.")


@app.command()
def ingest(
    source: Path = typer.Argument(
        ...,
        help="Directory containing knowledge base documents (.md, .txt, .rst, .pdf, .docx).",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    config: Path = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to simulation config file for RAG settings.",
        show_default=False,
    ),
    chunk_size: int = typer.Option(
        500,
        "--chunk-size",
        help="Maximum characters per chunk.",
        show_default=True,
    ),
    chunk_overlap: int = typer.Option(
        100,
        "--chunk-overlap",
        help="Character overlap between consecutive chunks.",
        show_default=True,
    ),
    default_roles: str = typer.Option(
        "",
        "--default-roles",
        help="Comma-separated default accessible roles for files without metadata.",
        show_default=False,
    ),
) -> None:
    """Ingest documents from a directory into the Qdrant knowledge store."""
    import asyncio
    import sys

    from entwine.rag.pipeline import ingest_directory
    from entwine.rag.settings import RAGSettings
    from entwine.rag.store import KnowledgeStore

    roles = [r.strip() for r in default_roles.split(",") if r.strip()] if default_roles else None

    # Build RAGSettings from config file if provided
    rag_settings: RAGSettings | None = None
    if config is not None:
        cfg = load_config(config)
        if cfg.rag is not None:
            rag_settings = cfg.rag

    def _progress(path: Path, chunks: int) -> None:
        if chunks == 0:
            typer.echo(f"  {path.name}: SKIPPED")
        else:
            typer.echo(f"  {path.name}: {chunks} chunks")

    async def _run() -> int:
        store = KnowledgeStore(settings=rag_settings)
        await store.init_collection()
        return await ingest_directory(
            source,
            store,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            default_roles=roles,
            progress_callback=_progress,
        )

    typer.echo(f"Ingesting documents from {source} ...")
    try:
        total = asyncio.run(_run())
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    typer.echo(f"Done. Ingested {total} document chunks.")


@app.command(name="evaluate-rag")
def evaluate_rag(
    dataset: Path = typer.Argument(
        ...,
        help="Path to evaluation dataset JSON file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """Evaluate RAG retrieval quality: dense-only vs hybrid (P@5, R@5, MRR)."""
    import asyncio
    import json

    from entwine.rag.evaluation import EvalQuery, evaluate
    from entwine.rag.settings import RAGSettings
    from entwine.rag.store import KnowledgeStore

    raw = json.loads(dataset.read_text(encoding="utf-8"))
    queries = [
        EvalQuery(
            query=q["query"],
            relevant_doc_ids=q.get("relevant_doc_stems", q.get("relevant_doc_ids", [])),
            role=q.get("role", "company-wide"),
        )
        for q in raw["queries"]
    ]
    typer.echo(f"Loaded {len(queries)} evaluation queries from {dataset}")

    async def _run_eval(hybrid: bool) -> list[list]:  # type: ignore[type-arg]
        settings = RAGSettings(enable_hybrid=hybrid)
        store = KnowledgeStore(settings=settings)
        await store.init_collection()
        results = []
        for q in queries:
            r = await store.search(q.query, agent_roles=[q.role], limit=5)
            results.append(r)
        return results

    async def _main() -> None:
        # Dense-only mode
        typer.echo("\nRunning dense-only evaluation...")
        dense_results = await _run_eval(hybrid=False)
        dense_metrics = evaluate(queries, dense_results, k=5)

        # Hybrid mode
        typer.echo("Running hybrid (dense + sparse + RRF) evaluation...")
        hybrid_results = await _run_eval(hybrid=True)
        hybrid_metrics = evaluate(queries, hybrid_results, k=5)

        typer.echo(f"\n{'Metric':<20} {'Dense-only':>12} {'Hybrid':>12}")
        typer.echo("-" * 46)
        typer.echo(
            f"{'Precision@5':<20} {dense_metrics.precision_at_k:>12.4f}"
            f" {hybrid_metrics.precision_at_k:>12.4f}"
        )
        typer.echo(
            f"{'Recall@5':<20} {dense_metrics.recall_at_k:>12.4f}"
            f" {hybrid_metrics.recall_at_k:>12.4f}"
        )
        typer.echo(f"{'MRR':<20} {dense_metrics.mrr:>12.4f} {hybrid_metrics.mrr:>12.4f}")
        typer.echo(f"\nQueries evaluated: {dense_metrics.num_queries}")

    asyncio.run(_main())


@app.command()
def version(
    short: bool = typer.Option(
        False,
        "--short",
        "-s",
        is_flag=True,
        help="Print only the version string.",
    ),
) -> None:
    """Print the entwine version."""
    if short:
        typer.echo(entwine.__version__)
    else:
        typer.echo(f"entwine {entwine.__version__}")
