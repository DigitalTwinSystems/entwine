"""entsim CLI — entry point for the entsim command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
import uvicorn
from pydantic import ValidationError

import entsim
from entsim.config.loader import load_config

app = typer.Typer(
    name="entsim",
    help="LLM-powered enterprise digital twin simulation.",
    no_args_is_help=True,
)

_DEFAULT_CONFIG = Path("entsim.yaml")


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
    from entsim.llm.router import LLMRouter
    from entsim.llm.settings import LLMSettings
    from entsim.simulation.engine import SimulationEngine
    from entsim.web.app import set_engine

    llm_settings = LLMSettings()
    llm_router = LLMRouter(settings=llm_settings)

    engine = SimulationEngine(cfg, llm_router=llm_router)
    set_engine(engine)

    typer.echo(
        f"Starting entsim — simulation: {cfg.simulation.name!r}, "
        f"agents: {agent_count}, "
        f"LLM: {llm_settings.standard_model}, "
        f"server: http://{host}:{port}"
    )

    uvicorn.run("entsim.web:app", host=host, port=port)


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
def version(
    short: bool = typer.Option(
        False,
        "--short",
        "-s",
        is_flag=True,
        help="Print only the version string.",
    ),
) -> None:
    """Print the entsim version."""
    if short:
        typer.echo(entsim.__version__)
    else:
        typer.echo(f"entsim {entsim.__version__}")
