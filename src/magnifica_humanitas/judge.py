"""Multi-stage Magnifica Humanitas judge.

Pipeline:
  1. assess_context          — establishes blast radius and operational context
  2. analyze_* (parallel)    — one call per component type
  3. synthesize              — aggregates component analyses → JudgeOutput

Uses pydantic-ai for provider-agnostic LLM calls. Model strings:
  "anthropic:claude-haiku-4-5-20251001"
  "openai:gpt-4o-mini"
  "google-gla:gemini-2.0-flash"
  "mistral:mistral-small-latest"

Per-component analyses default to a fast/cheap model; synthesis defaults to a
stronger model. Both can be overridden.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import logfire
from pydantic_ai import Agent

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

_PROMPT_CACHE: dict[str, str] = {}


def _prompt(name: str) -> str:
    if name not in _PROMPT_CACHE:
        _PROMPT_CACHE[name] = (_PROMPTS_DIR / f"{name}.md").read_text()
    return _PROMPT_CACHE[name]


def _make_agent(system_prompt: str, result_type: type) -> Agent:
    """Create a pydantic-ai Agent with no model pre-bound (model passed at run time)."""
    return Agent(system_prompt=system_prompt, result_type=result_type)


# Stage agents — created once at module import, model injected at run time
_CTX_AGENT = _make_agent(_prompt("context_assessment"), ContextAssessment)
_SP_AGENT  = _make_agent(_prompt("system_prompt"),      ComponentAnalysis)
_MCP_AGENT = _make_agent(_prompt("mcp"),                ComponentAnalysis)
_SKL_AGENT = _make_agent(_prompt("skill"),              ComponentAnalysis)
_SUB_AGENT = _make_agent(_prompt("subagent"),           ComponentAnalysis)
_SYN_AGENT = _make_agent(_prompt("synthesis"),          JudgeOutput)


def _context_header(ctx: ContextAssessment) -> str:
    return (
        f"Operational context: {ctx.operational_context}\n"
        f"Blast radius: {ctx.blast_radius} | Scale: {ctx.inferred_scale}"
    )


# ─── Stage 1 ─────────────────────────────────────────────────────────────────


@logfire.instrument("assess_context")
async def _assess_context(
    config: AgentConfig, model: str
) -> ContextAssessment:
    result = await _CTX_AGENT.run(
        f"Assess the operational context:\n\n{config.to_text()}",
        model=model,
    )
    ctx = result.data
    logfire.info("context_assessed", blast_radius=ctx.blast_radius, scale=ctx.inferred_scale)
    return ctx


# ─── Stage 2 ─────────────────────────────────────────────────────────────────


@logfire.instrument("analyze_system_prompt")
async def _analyze_system_prompt(
    system_prompt: str, ctx: ContextAssessment, model: str
) -> ComponentAnalysis:
    result = await _SP_AGENT.run(
        f"{_context_header(ctx)}\n\nAnalyze this system prompt:\n\n---\n{system_prompt}\n---",
        model=model,
    )
    return result.data


@logfire.instrument("analyze_mcp")
async def _analyze_mcp(
    mcp: MCPDefinition, ctx: ContextAssessment, model: str
) -> ComponentAnalysis:
    result = await _MCP_AGENT.run(
        f"{_context_header(ctx)}\n\nAnalyze this MCP:\n\n{mcp.model_dump_json(indent=2)}",
        model=model,
    )
    return result.data


@logfire.instrument("analyze_skill")
async def _analyze_skill(
    skill: SkillDefinition, ctx: ContextAssessment, model: str
) -> ComponentAnalysis:
    result = await _SKL_AGENT.run(
        f"{_context_header(ctx)}\n\nAnalyze this skill:\n\n{skill.model_dump_json(indent=2)}",
        model=model,
    )
    return result.data


@logfire.instrument("analyze_subagent")
async def _analyze_subagent(
    subagent: SubagentDefinition, ctx: ContextAssessment, model: str
) -> ComponentAnalysis:
    result = await _SUB_AGENT.run(
        f"{_context_header(ctx)}\n\nAnalyze this subagent:\n\n{subagent.model_dump_json(indent=2)}",
        model=model,
    )
    return result.data


async def _run_parallel(
    config: AgentConfig, ctx: ContextAssessment, model: str
) -> list[ComponentAnalysis]:
    """Dispatch all per-component analyses concurrently."""
    tasks: list[Any] = []

    if config.system_prompt:
        tasks.append(_analyze_system_prompt(config.system_prompt, ctx, model))

    for mcp in config.parsed_mcps():
        tasks.append(_analyze_mcp(mcp, ctx, model))

    for skill in config.parsed_skills():
        tasks.append(_analyze_skill(skill, ctx, model))

    for subagent in config.parsed_subagents():
        tasks.append(_analyze_subagent(subagent, ctx, model))

    return list(await asyncio.gather(*tasks))


# ─── Stage 3 ─────────────────────────────────────────────────────────────────


@logfire.instrument("synthesize")
async def _synthesize(
    ctx: ContextAssessment,
    analyses: list[ComponentAnalysis],
    model: str,
) -> JudgeOutput:
    import json
    analyses_json = json.dumps([a.model_dump() for a in analyses], indent=2)
    user_msg = (
        f"Context assessment:\n{ctx.model_dump_json(indent=2)}\n\n"
        f"Component analyses:\n{analyses_json}"
    )
    result = await _SYN_AGENT.run(user_msg, model=model)
    output = result.data
    logfire.info(
        "synthesis_complete",
        paradigm=output.overall_paradigm,
        confessions=len(output.confessions),
        high_recs=sum(1 for r in output.recommendations if r.priority == "high"),
        source=getattr(ctx, "_source", None),
    )
    return output


# ─── Public API ──────────────────────────────────────────────────────────────


async def judge_async(
    config: AgentConfig,
    *,
    model: str = "anthropic:claude-haiku-4-5-20251001",
    synthesis_model: str | None = None,
) -> JudgeOutput:
    """Async multi-stage judge. Works with any pydantic-ai supported model string.

    Args:
        config: The agent configuration to evaluate.
        model: Model for context + per-component analysis stages.
               Format: "provider:model-id" e.g. "openai:gpt-4o-mini"
        synthesis_model: Model for final synthesis. Defaults to Sonnet-class reasoning.
    """
    if synthesis_model is None:
        # Default to a Sonnet-class model; try to match the provider from `model`
        provider = model.split(":")[0] if ":" in model else "anthropic"
        synthesis_model = {
            "anthropic": "anthropic:claude-sonnet-4-6",
            "openai":    "openai:gpt-4o",
            "google-gla":"google-gla:gemini-2.0-flash",
            "mistral":   "mistral:mistral-large-latest",
            "groq":      "groq:llama-3.3-70b-versatile",
        }.get(provider, "anthropic:claude-sonnet-4-6")

    ctx = await _assess_context(config, model)
    analyses = await _run_parallel(config, ctx, model)
    return await _synthesize(ctx, analyses, synthesis_model)


def judge(
    config: AgentConfig,
    *,
    model: str = "anthropic:claude-haiku-4-5-20251001",
    synthesis_model: str | None = None,
) -> JudgeOutput:
    """Synchronous wrapper around judge_async."""
    return asyncio.run(judge_async(config, model=model, synthesis_model=synthesis_model))
