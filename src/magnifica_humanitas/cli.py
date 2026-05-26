"""CLI: mh-judge <config-file> or mh-judge --eval"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.text import Text

from .models import AgentConfig
from .observability import configure

app = typer.Typer(help="Magnifica Humanitas — LLM judge for coding agent configurations")
console = Console()


@app.command()
def judge_cmd(
    config_file: Path = typer.Argument(..., help="YAML or JSON file containing the agent config"),
    model: str = typer.Option("claude-opus-4-7-20251101", help="Claude model to use"),
    logfire_enabled: bool = typer.Option(True, "--logfire/--no-logfire"),
) -> None:
    """Judge a single agent configuration."""
    if logfire_enabled:
        configure()

    import yaml
    from .judge import judge

    raw = config_file.read_text()
    if config_file.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    config = AgentConfig.model_validate(data)

    with console.status("[bold]Consulting the encyclical...[/bold]"):
        output = judge(config, model=model)

    paradigm_color = {"Babel": "red", "Mixed": "yellow", "Nehemiah": "green"}[
        output.overall_paradigm
    ]
    console.print(
        Panel(
            Text(output.overall_paradigm, style=f"bold {paradigm_color}"),
            title="Overall Paradigm",
            expand=False,
        )
    )
    console.print(Panel(output.overall_summary, title="Summary"))
    console.print(Panel(JSON(output.model_dump_json(indent=2)), title="Full Assessment"))


@app.command()
def eval_cmd(
    logfire_enabled: bool = typer.Option(True, "--logfire/--no-logfire"),
) -> None:
    """Run the full pydantic-evals evaluation suite."""
    if logfire_enabled:
        configure()

    from .eval import run_eval
    asyncio.run(run_eval())


if __name__ == "__main__":
    app()
