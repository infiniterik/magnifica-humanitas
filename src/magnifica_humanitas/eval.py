"""pydantic-evals Dataset and Evaluators for the multi-stage Magnifica Humanitas judge."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
import logfire
from pydantic_evals import Dataset, Case
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .models import AgentConfig, JudgeOutput
from .judge import judge_async

_EXAMPLES_DIR = (
    Path(__file__).parent.parent.parent
    / ".claude"
    / "skills"
    / "magnifica-judge"
    / "examples"
)


# ─── Evaluators ──────────────────────────────────────────────────────────────


@dataclass
class ParadigmMatch(Evaluator[AgentConfig, JudgeOutput]):
    """Predicted paradigm matches expected."""

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        if ctx.expected_output is None:
            return {}
        return {
            "paradigm_match": int(
                ctx.output.overall_paradigm == ctx.expected_output.overall_paradigm
            )
        }


@dataclass
class DimensionScoreProximity(Evaluator[AgentConfig, JudgeOutput]):
    """Mean absolute error between expected and actual dimension scores."""

    threshold: float = 1.5

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        if ctx.expected_output is None:
            return {}
        expected = ctx.expected_output.dimension_scores
        actual = ctx.output.dimension_scores
        keys = set(expected) & set(actual)
        if not keys:
            return {}
        mae = sum(abs(expected[k].score - actual[k].score) for k in keys) / len(keys)
        return {
            "dimension_mae": mae,
            "dimension_within_threshold": int(mae <= self.threshold),
        }


@dataclass
class HasHighPriorityRecs(Evaluator[AgentConfig, JudgeOutput]):
    """Babel configs must generate ≥1 high-priority recommendation."""

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        if ctx.output.overall_paradigm != "Babel":
            return {}
        high = [r for r in ctx.output.recommendations if r.priority == "high"]
        return {"babel_has_high_priority_rec": int(len(high) > 0)}


@dataclass
class StructuralIntegrity(Evaluator[AgentConfig, JudgeOutput]):
    """All nine dimensions present and scored."""

    REQUIRED: frozenset[str] = frozenset({
        "human_primacy", "traceable_responsibility", "transparency",
        "subsidiarity", "technocratic_resistance", "care_for_affected",
        "limits_and_humility", "truth_and_non_manipulation", "irreversibility_caution",
    })

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        present = set(ctx.output.dimension_scores.keys())
        missing = self.REQUIRED - present
        return {
            "all_dimensions_present": int(len(missing) == 0),
            "missing_dimension_count": len(missing),
        }


@dataclass
class ConfessionHandled(Evaluator[AgentConfig, JudgeOutput]):
    """Configs with confessions produce a confessions list in the output."""

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        # Count confessions in the input config
        config = ctx.inputs
        confession_count = sum(
            1 for component_list in [
                config.parsed_mcps(),
                config.parsed_skills(),
                config.parsed_subagents(),
            ]
            for c in component_list
            if c.confession is not None
        )
        if confession_count == 0:
            return {}
        output_confessions = len(ctx.output.confessions)
        return {
            "confessions_in_input": confession_count,
            "confessions_in_output": output_confessions,
            "confessions_handled": int(output_confessions >= confession_count),
        }


# ─── Dataset ─────────────────────────────────────────────────────────────────


def _load_example(name: str) -> tuple[AgentConfig, JudgeOutput]:
    data = yaml.safe_load((_EXAMPLES_DIR / f"{name}.yaml").read_text())
    return (
        AgentConfig.model_validate(data["config"]),
        JudgeOutput.model_validate(data["expected_output"]),
    )


def _make_case(name: str) -> Case[AgentConfig, JudgeOutput, None]:
    config, expected = _load_example(name)
    return Case(
        name=name,
        inputs=config,
        expected_output=expected,
        evaluators=(
            ParadigmMatch(),
            DimensionScoreProximity(),
            HasHighPriorityRecs(),
            StructuralIntegrity(),
            ConfessionHandled(),
        ),
    )


def build_dataset() -> Dataset[AgentConfig, JudgeOutput, None]:
    return Dataset(cases=[_make_case(n) for n in ("babel", "nehemiah", "mixed")])


# ─── Task function ───────────────────────────────────────────────────────────


async def evaluate_config(config: AgentConfig) -> JudgeOutput:
    with logfire.span("eval_task", config_keys=list(config.model_fields_set)):
        return await judge_async(config)


# ─── Runner ──────────────────────────────────────────────────────────────────


async def run_eval() -> None:
    from .observability import configure
    configure()
    dataset = build_dataset()
    report = await dataset.evaluate(evaluate_config)
    report.print(include_input=False)
