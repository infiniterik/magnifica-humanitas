"""CLI: mh-judge judge <path-or-config> | mh-judge eval | mh-judge loaders"""
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

_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"
_DEFAULT_SYNTH  = None  # auto-matched to provider


@app.command()
def judge_cmd(
    target: Path = typer.Argument(
        ...,
        help=(
            "Path to judge. Pass a directory to auto-detect the agent framework "
            "(Claude Code, Codex, OpenCode, .agents/), or a YAML/JSON config file."
        ),
    ),
    model: str = typer.Option(
        _DEFAULT_MODEL,
        help=(
            "Model for per-component analysis. "
            "Format: provider:model-id — e.g. "
            "'openai:gpt-4o-mini', 'anthropic:claude-haiku-4-5-20251001', "
            "'google-gla:gemini-2.0-flash'"
        ),
    ),
    synthesis_model: str = typer.Option(
        "",
        help="Model for final synthesis. Defaults to a Sonnet-class model matching the provider.",
    ),
    logfire_enabled: bool = typer.Option(True, "--logfire/--no-logfire"),
    json_out: bool = typer.Option(False, "--json", help="Print full JSON output"),
) -> None:
    """Judge an agent configuration from a file or directory."""
    if logfire_enabled:
        configure()

    synth = synthesis_model or None

    # Load config
    if target.is_dir():
        from .loaders import load, detect
        loader = detect(target)
        if loader is None:
            console.print(
                f"[red]No recognized agent configuration at {target}[/red]\n"
                "Looked for: .claude/ (Claude Code), opencode.json (OpenCode), "
                "AGENTS.md / codex.json / config.toml (Codex), .agents/ (agents-folder)."
            )
            raise typer.Exit(1)
        console.print(f"[dim]Detected framework: [bold]{loader.framework_name}[/bold][/dim]")
        config = loader.load(target)
    else:
        import yaml
        raw = target.read_text()
        data = yaml.safe_load(raw) if target.suffix in {".yaml", ".yml"} else json.loads(raw)
        config = AgentConfig.model_validate(data)

    # Count components
    n_mcps   = len(config.mcps or [])
    n_skills = len(config.skills or [])
    n_agents = len(config.subagents or [])
    has_sp   = config.system_prompt is not None
    total    = (1 if has_sp else 0) + n_mcps + n_skills + n_agents
    provider = model.split(":")[0] if ":" in model else model

    console.print(
        f"\n[bold]Magnifica Humanitas[/bold] · {provider} · "
        + (f"source: {config.source} · " if config.source else "")
        + f"{total} component{'s' if total != 1 else ''} "
        f"({'SP + ' if has_sp else ''}{n_mcps}M {n_skills}Sk {n_agents}SA)\n"
    )

    from .judge import judge
    with console.status("[bold]Running pipeline…[/bold]"):
        output = judge(config, model=model, synthesis_model=synth)

    # Paradigm banner
    color = _PARADIGM_COLOR[output.overall_paradigm]
    console.print(Panel(
        Text(f"  {output.overall_paradigm}  ", style=f"bold {color} on {color}3", justify="center"),
        title="Overall Paradigm",
        expand=False,
    ))
    console.print(f"\n{output.overall_summary}\n")

    # Dimension scores
    table = Table(title="Dimension Scores", show_header=True, header_style="bold")
    table.add_column("Dimension", style="dim", width=28)
    table.add_column("Score", justify="center", width=7)
    table.add_column("Concerns", overflow="fold")
    for key, dim in output.dimension_scores.items():
        label = key.replace("_", " ").title()
        score_text = Text(str(dim.score), style=_SCORE_COLOR.get(dim.score, "white"))
        table.add_row(label, score_text, dim.concerns or dim.evidence)
    console.print(table)

    # Confessions
    if output.confessions:
        console.print("\n[bold]Confessions heard[/bold]")
        for c in output.confessions:
            vc = {"justified": "green", "partially_justified": "yellow", "unjustified": "red"}.get(c.verdict, "white")
            console.print(
                f"  [{vc}]{c.verdict.upper()}[/{vc}] "
                f"[bold]{c.component_name}[/bold]: "
                f"{c.acknowledgment[:120]}{'…' if len(c.acknowledgment) > 120 else ''}"
            )

    # Recommendations
    if output.recommendations:
        console.print("\n[bold]Recommendations[/bold]")
        for rec in output.recommendations:
            pc = _PRIORITY_COLOR.get(rec.priority, "white")
            console.print(f"  [{pc}][{rec.priority.upper()}][/{pc}] [bold]{rec.component}[/bold]: {rec.change}")

    if json_out:
        console.print(Panel(JSON(output.model_dump_json(indent=2)), title="Full JSON"))


@app.command()
def eval_cmd(
    logfire_enabled: bool = typer.Option(True, "--logfire/--no-logfire"),
) -> None:
    """Run the pydantic-evals suite against the three calibration cases."""
    if logfire_enabled:
        configure()
    from .eval import run_eval
    asyncio.run(run_eval())


@app.command()
def loaders_cmd() -> None:
    """List available config loaders and the frameworks they support."""
    from .loaders import available_loaders, _LOADERS

    table = Table(title="Available Loaders", show_header=True, header_style="bold")
    table.add_column("Framework", style="bold")
    table.add_column("Detects")
    detectors = {
        "claude-code": ".claude/ directory",
        "opencode":    "opencode.json or opencode.toml",
        "codex":       "AGENTS.md, codex.json, .codex/config.toml",
        "agents-folder": ".agents/manifest.yaml or AGENTS.md",
    }
    for loader in _LOADERS:
        table.add_row(loader.framework_name, detectors.get(loader.framework_name, "—"))
    console.print(table)
    console.print("\nPass a directory to [bold]mh-judge judge <dir>[/bold] to auto-detect.")


app.command(name="loaders")(loaders_cmd)

if __name__ == "__main__":
    app()
