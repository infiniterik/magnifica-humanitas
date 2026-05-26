"""pydantic-evals Dataset and Evaluators for the Magnifica Humanitas judge."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
import logfire
from pydantic_evals import Dataset, Case
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from .models import AgentConfig, JudgeOutput
from .judge import judge

_EXAMPLES_DIR = (
    Path(__file__).parent.parent.parent
    / ".claude"
    / "skills"
    / "magnifica-judge"
    / "examples"
)


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


@dataclass
class ParadigmMatch(Evaluator[AgentConfig, JudgeOutput]):
    """Checks whether the predicted paradigm matches the expected one."""

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        if ctx.expected_output is None:
            return {}
        expected = ctx.expected_output.overall_paradigm
        actual = ctx.output.overall_paradigm
        return {"paradigm_match": int(expected == actual)}


@dataclass
class DimensionScoreProximity(Evaluator[AgentConfig, JudgeOutput]):
    """Mean absolute error between expected and actual dimension scores (lower = better)."""

    threshold: float = 1.5

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        if ctx.expected_output is None:
            return {}

        expected_scores = ctx.expected_output.dimension_scores
        actual_scores = ctx.output.dimension_scores

        keys = set(expected_scores) & set(actual_scores)
        if not keys:
            return {}

        mae = sum(
            abs(expected_scores[k].score - actual_scores[k].score) for k in keys
        ) / len(keys)

        return {
            "dimension_mae": mae,
            "dimension_within_threshold": int(mae <= self.threshold),
        }


@dataclass
class HasHighPriorityRecs(Evaluator[AgentConfig, JudgeOutput]):
    """Verifies that Babel configs generate at least one high-priority recommendation."""

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        if ctx.output.overall_paradigm != "Babel":
            return {}
        high_recs = [r for r in ctx.output.recommendations if r.priority == "high"]
        return {"babel_has_high_priority_rec": int(len(high_recs) > 0)}


@dataclass
class StructuralIntegrity(Evaluator[AgentConfig, JudgeOutput]):
    """Checks that all nine required dimensions are present and scored."""

    REQUIRED_DIMENSIONS = {
        "human_primacy",
        "traceable_responsibility",
        "transparency",
        "subsidiarity",
        "technocratic_resistance",
        "care_for_affected",
        "limits_and_humility",
        "truth_and_non_manipulation",
        "irreversibility_caution",
    }

    async def evaluate(
        self, ctx: EvaluatorContext[AgentConfig, JudgeOutput]
    ) -> dict[str, Any]:
        present = set(ctx.output.dimension_scores.keys())
        missing = self.REQUIRED_DIMENSIONS - present
        return {
            "all_dimensions_present": int(len(missing) == 0),
            "missing_dimension_count": len(missing),
        }


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------


def _load_example(name: str) -> tuple[AgentConfig, JudgeOutput]:
    path = _EXAMPLES_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text())
    config = AgentConfig.model_validate(data["config"])
    expected = JudgeOutput.model_validate(data["expected_output"])
    return config, expected


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
        ),
    )


def build_dataset() -> Dataset[AgentConfig, JudgeOutput, None]:
    cases = [_make_case(name) for name in ("babel", "nehemiah", "mixed")]
    return Dataset(cases=cases)


# ---------------------------------------------------------------------------
# Task function (what pydantic-evals calls to get the output)
# ---------------------------------------------------------------------------


async def evaluate_config(config: AgentConfig) -> JudgeOutput:
    """Async wrapper so pydantic-evals can call the judge."""
    with logfire.span("eval_task", config_keys=list(config.model_fields_set)):
        return judge(config)


# ---------------------------------------------------------------------------
# CLI entry point for running the full eval
# ---------------------------------------------------------------------------


async def run_eval() -> None:
    from .observability import configure
    configure()
    dataset = build_dataset()
    report = await dataset.evaluate(evaluate_config)
    report.print(include_input=False)
