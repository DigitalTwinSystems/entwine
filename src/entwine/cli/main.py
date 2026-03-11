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
    directory: Path = typer.Argument(
        ...,
        help="Directory containing knowledge base documents (.md, .txt, .rst).",
        exists=True,
        file_okay=False,
        dir_okay=True,
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
) -> None:
    """Ingest documents from a directory into the Qdrant knowledge store."""
    import asyncio

    from entwine.rag.pipeline import ingest_directory
    from entwine.rag.store import KnowledgeStore

    async def _run() -> int:
        store = KnowledgeStore()
        await store.init_collection()
        return await ingest_directory(
            directory,
            store,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    typer.echo(f"Ingesting documents from {directory} ...")
    total = asyncio.run(_run())
    typer.echo(f"Done. Ingested {total} document chunks.")


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
