"""CLI: mh-judge judge <config-file> | mh-judge eval"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import AgentConfig
from .observability import configure

app = typer.Typer(help="Magnifica Humanitas — LLM judge for coding agent configurations")
console = Console()

_PARADIGM_COLOR = {"Babel": "red", "Mixed": "yellow", "Nehemiah": "green"}
_PRIORITY_COLOR = {"high": "red", "medium": "yellow", "low": "dim"}
_SCORE_COLOR = {1: "red", 2: "orange3", 3: "yellow", 4: "green3", 5: "bold green"}


@app.command()
def judge_cmd(
    config_file: Path = typer.Argument(..., help="YAML or JSON agent config file"),
    model: str = typer.Option(
        "claude-haiku-4-5-20251001",
        help="Model for per-component analysis (default: Haiku for speed)",
    ),
    synthesis_model: str = typer.Option(
        "claude-sonnet-4-6",
        help="Model for final synthesis (default: Sonnet)",
    ),
    logfire_enabled: bool = typer.Option(True, "--logfire/--no-logfire"),
    json_out: bool = typer.Option(False, "--json", help="Print full JSON output"),
) -> None:
    """Judge a single agent configuration using the multi-stage pipeline."""
    if logfire_enabled:
        configure()

    import yaml
    from .judge import judge

    raw = config_file.read_text()
    data = yaml.safe_load(raw) if config_file.suffix in {".yaml", ".yml"} else json.loads(raw)
    config = AgentConfig.model_validate(data)

    # Count components for progress display
    n_mcps = len(config.mcps or [])
    n_skills = len(config.skills or [])
    n_agents = len(config.subagents or [])
    has_sp = config.system_prompt is not None
    total = (1 if has_sp else 0) + n_mcps + n_skills + n_agents

    console.print(
        f"\n[bold]Magnifica Humanitas[/bold] — analyzing "
        f"{'system prompt, ' if has_sp else ''}"
        f"{n_mcps} MCP{'s' if n_mcps != 1 else ''}, "
        f"{n_skills} skill{'s' if n_skills != 1 else ''}, "
        f"{n_agents} subagent{'s' if n_agents != 1 else ''} "
        f"({total} component{'s' if total != 1 else ''} in parallel)\n"
    )

    with console.status("[bold]Running pipeline…[/bold]"):
        output = judge(config, model=model, synthesis_model=synthesis_model)

    # ─── Paradigm banner ─────────────────────────────────────
    color = _PARADIGM_COLOR[output.overall_paradigm]
    console.print(
        Panel(
            Text(f"  {output.overall_paradigm}  ", style=f"bold {color} on {color}3",
                 justify="center"),
            title="Overall Paradigm",
            expand=False,
        )
    )
    console.print(f"\n{output.overall_summary}\n")

    # ─── Dimension scores ─────────────────────────────────────
    table = Table(title="Dimension Scores", show_header=True, header_style="bold")
    table.add_column("Dimension", style="dim", width=28)
    table.add_column("Score", justify="center", width=7)
    table.add_column("Concerns", overflow="fold")

    for key, dim in output.dimension_scores.items():
        label = key.replace("_", " ").title()
        score_text = Text(str(dim.score), style=_SCORE_COLOR.get(dim.score, "white"))
        table.add_row(label, score_text, dim.concerns or dim.evidence)

    console.print(table)

    # ─── Confessions ─────────────────────────────────────────
    if output.confessions:
        console.print("\n[bold]Confessions heard[/bold]")
        for c in output.confessions:
            verdict_color = {
                "justified": "green", "partially_justified": "yellow", "unjustified": "red"
            }.get(c.verdict, "white")
            console.print(
                f"  [{verdict_color}]{c.verdict.upper()}[/{verdict_color}] "
                f"[bold]{c.component_name}[/bold] ({c.component_type}): "
                f"{c.acknowledgment[:100]}{'…' if len(c.acknowledgment) > 100 else ''}"
            )

    # ─── Recommendations ─────────────────────────────────────
    if output.recommendations:
        console.print("\n[bold]Recommendations[/bold]")
        for rec in output.recommendations:
            pc = _PRIORITY_COLOR.get(rec.priority, "white")
            console.print(
                f"  [{pc}][{rec.priority.upper()}][/{pc}] "
                f"[bold]{rec.component}[/bold]: {rec.change}"
            )

    if json_out:
        console.print(Panel(JSON(output.model_dump_json(indent=2)), title="Full JSON"))


@app.command()
def eval_cmd(
    logfire_enabled: bool = typer.Option(True, "--logfire/--no-logfire"),
) -> None:
    """Run the full pydantic-evals evaluation suite against the three calibration cases."""
    if logfire_enabled:
        configure()
    from .eval import run_eval
    asyncio.run(run_eval())


if __name__ == "__main__":
    app()
