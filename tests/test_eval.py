"""Tests for models, evaluators, and the dataset."""
from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from magnifica_humanitas.models import (
    AgentConfig,
    Confession,
    JudgeOutput,
    MCPDefinition,
    SkillDefinition,
    SubagentDefinition,
)
from magnifica_humanitas.eval import (
    ParadigmMatch,
    DimensionScoreProximity,
    HasHighPriorityRecs,
    StructuralIntegrity,
    ConfessionHandled,
    build_dataset,
)

EXAMPLES_DIR = (
    Path(__file__).parent.parent
    / ".claude"
    / "skills"
    / "magnifica-judge"
    / "examples"
)


def _load(name: str) -> tuple[AgentConfig, JudgeOutput]:
    data = yaml.safe_load((EXAMPLES_DIR / f"{name}.yaml").read_text())
    return (
        AgentConfig.model_validate(data["config"]),
        JudgeOutput.model_validate(data["expected_output"]),
    )


# ─── Model validation ────────────────────────────────────────────────────────

class TestExampleLoading:
    def test_babel_loads(self):
        config, output = _load("babel")
        assert output.overall_paradigm == "Babel"
        assert len(output.dimension_scores) == 9

    def test_nehemiah_loads(self):
        _, output = _load("nehemiah")
        assert output.overall_paradigm == "Nehemiah"

    def test_mixed_loads(self):
        _, output = _load("mixed")
        assert output.overall_paradigm == "Mixed"

    def test_all_scores_in_range(self):
        for name in ("babel", "nehemiah", "mixed"):
            _, output = _load(name)
            for key, dim in output.dimension_scores.items():
                assert 1 <= dim.score <= 5, f"{name}/{key} out of range"

    def test_recommendation_priorities_valid(self):
        for name in ("babel", "nehemiah", "mixed"):
            _, output = _load(name)
            for rec in output.recommendations:
                assert rec.priority in {"high", "medium", "low"}


class TestConfessionParsing:
    def test_mcp_string_confession(self):
        mcp = MCPDefinition.from_dict({
            "name": "prod-db",
            "confession": "I know drop_table is ungated.",
        })
        assert mcp.confession is not None
        assert "drop_table" in mcp.confession.acknowledgment

    def test_mcp_structured_confession(self):
        mcp = MCPDefinition.from_dict({
            "name": "prod-db",
            "confession": {
                "acknowledgment": "drop_table is ungated.",
                "justification": "Test fixtures only.",
            },
        })
        assert mcp.confession.justification == "Test fixtures only."

    def test_skill_no_confession(self):
        skill = SkillDefinition.from_dict({"name": "code-review", "content": "..."})
        assert skill.confession is None

    def test_subagent_string_confession(self):
        sub = SubagentDefinition.from_dict({
            "name": "auto-deploy",
            "confession": "This bypasses review because the product moves fast.",
        })
        assert sub.confession is not None

    def test_agent_config_parsed_mcps(self):
        config = AgentConfig(
            mcps=[{"name": "github", "confession": "Broad access by design."}]
        )
        mcps = config.parsed_mcps()
        assert len(mcps) == 1
        assert mcps[0].confession is not None


class TestAgentConfigToText:
    def test_all_sections_present(self):
        config = AgentConfig(
            system_prompt="You are helpful.",
            mcps=[{"name": "gh"}],
            skills=[{"name": "review"}],
            subagents=[{"name": "searcher"}],
        )
        text = config.to_text()
        assert "System Prompt" in text
        assert "MCP Servers" in text
        assert "Skills" in text
        assert "Subagents" in text

    def test_empty_config(self):
        assert AgentConfig().to_text() == "(empty configuration)"


# ─── Dataset ─────────────────────────────────────────────────────────────────

class TestDataset:
    def test_builds_three_cases(self):
        ds = build_dataset()
        assert len(ds.cases) == 3
        assert {c.name for c in ds.cases} == {"babel", "nehemiah", "mixed"}

    def test_all_cases_have_evaluators(self):
        ds = build_dataset()
        for case in ds.cases:
            assert len(case.evaluators) == 5


# ─── Evaluators ──────────────────────────────────────────────────────────────

class TestEvaluators:
    def _ctx(self, output, expected=None, inputs=None):
        from pydantic_evals.evaluators import EvaluatorContext
        config, _ = _load("babel")
        return EvaluatorContext(
            inputs=inputs or config,
            output=output,
            expected_output=expected,
        )

    @pytest.mark.asyncio
    async def test_paradigm_match_correct(self):
        _, expected = _load("babel")
        ctx = self._ctx(expected, expected)
        assert (await ParadigmMatch().evaluate(ctx))["paradigm_match"] == 1

    @pytest.mark.asyncio
    async def test_paradigm_match_wrong(self):
        _, expected = _load("babel")
        wrong = expected.model_copy(update={"overall_paradigm": "Nehemiah"})
        ctx = self._ctx(wrong, expected)
        assert (await ParadigmMatch().evaluate(ctx))["paradigm_match"] == 0

    @pytest.mark.asyncio
    async def test_structural_integrity_full(self):
        _, expected = _load("nehemiah")
        ctx = self._ctx(expected)
        result = await StructuralIntegrity().evaluate(ctx)
        assert result["all_dimensions_present"] == 1
        assert result["missing_dimension_count"] == 0

    @pytest.mark.asyncio
    async def test_babel_has_high_priority_rec(self):
        _, expected = _load("babel")
        ctx = self._ctx(expected)
        result = await HasHighPriorityRecs().evaluate(ctx)
        assert result["babel_has_high_priority_rec"] == 1

    @pytest.mark.asyncio
    async def test_nehemiah_skips_high_priority_check(self):
        _, expected = _load("nehemiah")
        ctx = self._ctx(expected)
        assert await HasHighPriorityRecs().evaluate(ctx) == {}

    @pytest.mark.asyncio
    async def test_dimension_mae_perfect(self):
        _, expected = _load("mixed")
        ctx = self._ctx(expected, expected)
        result = await DimensionScoreProximity().evaluate(ctx)
        assert result["dimension_mae"] == 0.0
        assert result["dimension_within_threshold"] == 1

    @pytest.mark.asyncio
    async def test_confession_handled_no_confessions(self):
        config, expected = _load("babel")
        ctx = self._ctx(expected, inputs=config)
        # babel.yaml has no confessions in config
        result = await ConfessionHandled().evaluate(ctx)
        assert result == {}

    @pytest.mark.asyncio
    async def test_confession_handled_with_confession(self):
        config = AgentConfig(
            mcps=[{"name": "prod-db", "confession": "drop_table is ungated."}]
        )
        _, expected = _load("babel")
        output_with_confession = expected.model_copy(
            update={"confessions": [
                {"component_type": "mcp", "component_name": "prod-db",
                 "acknowledgment": "drop_table is ungated.",
                 "verdict": "unjustified", "verdict_rationale": "No valid reason."}
            ]}
        )
        ctx = self._ctx(output_with_confession, inputs=config)
        result = await ConfessionHandled().evaluate(ctx)
        assert result["confessions_in_input"] == 1
        assert result["confessions_handled"] == 1
