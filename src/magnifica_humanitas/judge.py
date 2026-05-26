"""Multi-stage Magnifica Humanitas judge.

Pipeline:
  1. assess_context          — establishes blast radius and operational context
  2. analyze_* (parallel)    — one call per component type
  3. synthesize              — aggregates component analyses → JudgeOutput

Each stage loads its own focused system prompt so smaller models can handle it.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic
import logfire

from .models import (
    AgentConfig,
    ComponentAnalysis,
    ContextAssessment,
    JudgeOutput,
    MCPDefinition,
    SkillDefinition,
    SubagentDefinition,
)

_PROMPTS_DIR = (
    Path(__file__).parent.parent.parent
    / ".claude"
    / "skills"
    / "magnifica-judge"
    / "prompts"
)

# Prompt cache — loaded once per process
_PROMPT_CACHE: dict[str, str] = {}


def _prompt(name: str) -> str:
    if name not in _PROMPT_CACHE:
        _PROMPT_CACHE[name] = (_PROMPTS_DIR / f"{name}.md").read_text()
    return _PROMPT_CACHE[name]


def _parse(raw: str, model_cls: type) -> Any:
    """Strip optional markdown fences and validate against a Pydantic model."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()
    return model_cls.model_validate(json.loads(text))


def _call(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


# ─── Stage 1: Context ────────────────────────────────────────────────────────


@logfire.instrument("assess_context")
def assess_context(
    config: AgentConfig,
    client: anthropic.Anthropic,
    model: str,
) -> ContextAssessment:
    raw = _call(
        client,
        model,
        _prompt("context_assessment"),
        f"Assess the operational context of this configuration:\n\n{config.to_text()}",
        max_tokens=512,
    )
    result = _parse(raw, ContextAssessment)
    logfire.info("context_assessed", blast_radius=result.blast_radius, scale=result.inferred_scale)
    return result


# ─── Stage 2: Per-component analyses (run in parallel) ───────────────────────


def _context_header(ctx: ContextAssessment) -> str:
    return (
        f"Operational context: {ctx.operational_context}\n"
        f"Blast radius: {ctx.blast_radius} | Scale: {ctx.inferred_scale}"
    )


@logfire.instrument("analyze_system_prompt")
def analyze_system_prompt(
    system_prompt: str,
    ctx: ContextAssessment,
    client: anthropic.Anthropic,
    model: str,
) -> ComponentAnalysis:
    user = (
        f"{_context_header(ctx)}\n\n"
        f"Analyze this system prompt:\n\n---\n{system_prompt}\n---"
    )
    raw = _call(client, model, _prompt("system_prompt"), user, max_tokens=1024)
    return _parse(raw, ComponentAnalysis)


@logfire.instrument("analyze_mcp")
def analyze_mcp(
    mcp: MCPDefinition,
    ctx: ContextAssessment,
    client: anthropic.Anthropic,
    model: str,
) -> ComponentAnalysis:
    user = (
        f"{_context_header(ctx)}\n\n"
        f"Analyze this MCP:\n\n{mcp.model_dump_json(indent=2)}"
    )
    raw = _call(client, model, _prompt("mcp"), user, max_tokens=768)
    return _parse(raw, ComponentAnalysis)


@logfire.instrument("analyze_skill")
def analyze_skill(
    skill: SkillDefinition,
    ctx: ContextAssessment,
    client: anthropic.Anthropic,
    model: str,
) -> ComponentAnalysis:
    user = (
        f"{_context_header(ctx)}\n\n"
        f"Analyze this skill:\n\n{skill.model_dump_json(indent=2)}"
    )
    raw = _call(client, model, _prompt("skill"), user, max_tokens=768)
    return _parse(raw, ComponentAnalysis)


@logfire.instrument("analyze_subagent")
def analyze_subagent(
    subagent: SubagentDefinition,
    ctx: ContextAssessment,
    client: anthropic.Anthropic,
    model: str,
) -> ComponentAnalysis:
    user = (
        f"{_context_header(ctx)}\n\n"
        f"Analyze this subagent:\n\n{subagent.model_dump_json(indent=2)}"
    )
    raw = _call(client, model, _prompt("subagent"), user, max_tokens=768)
    return _parse(raw, ComponentAnalysis)


# ─── Stage 3: Synthesis ───────────────────────────────────────────────────────


@logfire.instrument("synthesize")
def synthesize(
    ctx: ContextAssessment,
    analyses: list[ComponentAnalysis],
    client: anthropic.Anthropic,
    model: str,
) -> JudgeOutput:
    analyses_json = json.dumps(
        [a.model_dump() for a in analyses], indent=2
    )
    user = (
        f"Context assessment:\n{ctx.model_dump_json(indent=2)}\n\n"
        f"Component analyses:\n{analyses_json}"
    )
    raw = _call(client, model, _prompt("synthesis"), user, max_tokens=2048)
    result = _parse(raw, JudgeOutput)
    logfire.info(
        "synthesis_complete",
        paradigm=result.overall_paradigm,
        confessions=len(result.confessions),
        high_recs=sum(1 for r in result.recommendations if r.priority == "high"),
    )
    return result


# ─── Async helpers for parallel component analysis ────────────────────────────


async def _run_parallel(
    config: AgentConfig,
    ctx: ContextAssessment,
    client: anthropic.Anthropic,
    model: str,
) -> list[ComponentAnalysis]:
    """Run all per-component analyses concurrently using a thread pool."""
    loop = asyncio.get_event_loop()

    tasks: list[asyncio.Future] = []

    if config.system_prompt:
        tasks.append(
            loop.run_in_executor(
                None, analyze_system_prompt, config.system_prompt, ctx, client, model
            )
        )

    for mcp in config.parsed_mcps():
        tasks.append(loop.run_in_executor(None, analyze_mcp, mcp, ctx, client, model))

    for skill in config.parsed_skills():
        tasks.append(loop.run_in_executor(None, analyze_skill, skill, ctx, client, model))

    for subagent in config.parsed_subagents():
        tasks.append(
            loop.run_in_executor(None, analyze_subagent, subagent, ctx, client, model)
        )

    return list(await asyncio.gather(*tasks))


# ─── Public entrypoints ───────────────────────────────────────────────────────


@logfire.instrument("judge", extract_args=True)
def judge(
    config: AgentConfig,
    *,
    model: str = "claude-haiku-4-5-20251001",
    synthesis_model: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> JudgeOutput:
    """Synchronous multi-stage judge.

    Component analyses run on the component_model (defaults to Haiku for speed/cost).
    Synthesis runs on synthesis_model (defaults to Sonnet for reasoning depth).

    Args:
        config: The agent configuration to evaluate.
        model: Model for context assessment and per-component analysis.
        synthesis_model: Model for final synthesis. Defaults to claude-sonnet-4-6.
        client: Optional pre-configured Anthropic client.
    """
    if client is None:
        client = anthropic.Anthropic()
    if synthesis_model is None:
        synthesis_model = "claude-sonnet-4-6"

    ctx = assess_context(config, client, model)
    analyses = asyncio.run(_run_parallel(config, ctx, client, model))
    return synthesize(ctx, analyses, client, synthesis_model)


async def judge_async(
    config: AgentConfig,
    *,
    model: str = "claude-haiku-4-5-20251001",
    synthesis_model: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> JudgeOutput:
    """Async variant for use inside async contexts (e.g. pydantic-evals)."""
    if client is None:
        client = anthropic.Anthropic()
    if synthesis_model is None:
        synthesis_model = "claude-sonnet-4-6"

    loop = asyncio.get_event_loop()
    ctx = await loop.run_in_executor(None, assess_context, config, client, model)
    analyses = await _run_parallel(config, ctx, client, model)
    return await loop.run_in_executor(
        None, synthesize, ctx, analyses, client, synthesis_model
    )
