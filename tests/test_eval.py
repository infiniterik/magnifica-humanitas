"""Tests for the evaluation suite and judge models."""
from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from magnifica_humanitas.models import AgentConfig, JudgeOutput
from magnifica_humanitas.eval import (
    ParadigmMatch,
    DimensionScoreProximity,
    HasHighPriorityRecs,
    StructuralIntegrity,
    build_dataset,
)

EXAMPLES_DIR = (
    Path(__file__).parent.parent
    / ".claude"
    / "skills"
    / "magnifica-judge"
    / "examples"
)


def _load_example(name: str) -> tuple[AgentConfig, JudgeOutput]:
    data = yaml.safe_load((EXAMPLES_DIR / f"{name}.yaml").read_text())
    return (
        AgentConfig.model_validate(data["config"]),
        JudgeOutput.model_validate(data["expected_output"]),
    )


class TestModelValidation:
    def test_babel_example_loads(self):
        config, output = _load_example("babel")
        assert output.overall_paradigm == "Babel"
        assert len(output.dimension_scores) == 9

    def test_nehemiah_example_loads(self):
        config, output = _load_example("nehemiah")
        assert output.overall_paradigm == "Nehemiah"
        assert len(output.dimension_scores) == 9

    def test_mixed_example_loads(self):
        config, output = _load_example("mixed")
        assert output.overall_paradigm == "Mixed"
        assert len(output.dimension_scores) == 9

    def test_dimension_scores_in_range(self):
        for name in ("babel", "nehemiah", "mixed"):
            _, output = _load_example(name)
            for dim_key, dim in output.dimension_scores.items():
                assert 1 <= dim.score <= 5, f"{name}/{dim_key} score out of range"

    def test_recommendations_have_valid_priorities(self):
        for name in ("babel", "nehemiah", "mixed"):
            _, output = _load_example(name)
            for rec in output.recommendations:
                assert rec.priority in {"high", "medium", "low"}

    def test_agent_config_to_text_with_all_fields(self):
        config = AgentConfig(
            system_prompt="You are an agent.",
            mcps=[{"name": "test-mcp"}],
            skills=[{"name": "test-skill"}],
            subagents=[{"name": "test-subagent"}],
        )
        text = config.to_text()
        assert "System Prompt" in text
        assert "MCP Servers" in text
        assert "Skills" in text
        assert "Subagents" in text

    def test_agent_config_to_text_empty(self):
        config = AgentConfig()
        assert config.to_text() == "(empty configuration)"


class TestDataset:
    def test_dataset_builds_without_error(self):
        dataset = build_dataset()
        assert len(dataset.cases) == 3
        names = {c.name for c in dataset.cases}
        assert names == {"babel", "nehemiah", "mixed"}


class TestEvaluators:
    """Unit tests for evaluators using the expected outputs as mock model outputs."""

    @pytest.mark.asyncio
    async def test_paradigm_match_correct(self):
        from pydantic_evals.evaluators import EvaluatorContext
        config, expected = _load_example("babel")
        ctx = EvaluatorContext(inputs=config, output=expected, expected_output=expected)
        result = await ParadigmMatch().evaluate(ctx)
        assert result["paradigm_match"] == 1

    @pytest.mark.asyncio
    async def test_paradigm_match_wrong(self):
        from pydantic_evals.evaluators import EvaluatorContext
        config, expected = _load_example("babel")
        wrong = expected.model_copy(update={"overall_paradigm": "Nehemiah"})
        ctx = EvaluatorContext(inputs=config, output=wrong, expected_output=expected)
        result = await ParadigmMatch().evaluate(ctx)
        assert result["paradigm_match"] == 0

    @pytest.mark.asyncio
    async def test_structural_integrity_all_present(self):
        from pydantic_evals.evaluators import EvaluatorContext
        config, expected = _load_example("nehemiah")
        ctx = EvaluatorContext(inputs=config, output=expected, expected_output=None)
        result = await StructuralIntegrity().evaluate(ctx)
        assert result["all_dimensions_present"] == 1
        assert result["missing_dimension_count"] == 0

    @pytest.mark.asyncio
    async def test_babel_has_high_priority_rec(self):
        from pydantic_evals.evaluators import EvaluatorContext
        config, expected = _load_example("babel")
        ctx = EvaluatorContext(inputs=config, output=expected, expected_output=None)
        result = await HasHighPriorityRecs().evaluate(ctx)
        assert result["babel_has_high_priority_rec"] == 1

    @pytest.mark.asyncio
    async def test_babel_high_priority_rec_skipped_for_nehemiah(self):
        from pydantic_evals.evaluators import EvaluatorContext
        config, expected = _load_example("nehemiah")
        ctx = EvaluatorContext(inputs=config, output=expected, expected_output=None)
        result = await HasHighPriorityRecs().evaluate(ctx)
        assert result == {}  # Not applicable to Nehemiah paradigm

    @pytest.mark.asyncio
    async def test_dimension_proximity_perfect_match(self):
        from pydantic_evals.evaluators import EvaluatorContext
        config, expected = _load_example("mixed")
        ctx = EvaluatorContext(inputs=config, output=expected, expected_output=expected)
        result = await DimensionScoreProximity().evaluate(ctx)
        assert result["dimension_mae"] == 0.0
        assert result["dimension_within_threshold"] == 1
