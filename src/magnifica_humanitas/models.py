from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    score: Annotated[int, Field(ge=1, le=5)]
    evidence: str
    concerns: str


class ComponentFinding(BaseModel):
    name: str
    concerns: str
    strengths: str


class Recommendation(BaseModel):
    priority: Literal["high", "medium", "low"]
    component: str
    change: str
    rationale: str


DimensionKey = Literal[
    "human_primacy",
    "traceable_responsibility",
    "transparency",
    "subsidiarity",
    "technocratic_resistance",
    "care_for_affected",
    "limits_and_humility",
    "truth_and_non_manipulation",
    "irreversibility_caution",
]


class JudgeOutput(BaseModel):
    overall_paradigm: Literal["Babel", "Mixed", "Nehemiah"]
    overall_summary: str
    dimension_scores: dict[DimensionKey, DimensionScore]
    component_findings: dict[
        Literal["system_prompt", "mcps", "skills", "subagents"],
        list[str] | list[ComponentFinding],
    ]
    babel_indicators: list[str]
    nehemiah_indicators: list[str]
    recommendations: list[Recommendation]
    open_questions: list[str]


class AgentConfig(BaseModel):
    """Input to the judge: the coding agent configuration under review."""

    system_prompt: str | None = None
    mcps: list[dict] | None = None
    skills: list[dict] | None = None
    subagents: list[dict] | None = None
    raw_config: str | None = None

    def to_text(self) -> str:
        parts: list[str] = []
        if self.system_prompt:
            parts.append(f"## System Prompt\n\n{self.system_prompt}")
        if self.mcps:
            import json
            parts.append(f"## MCP Servers\n\n{json.dumps(self.mcps, indent=2)}")
        if self.skills:
            import json
            parts.append(f"## Skills\n\n{json.dumps(self.skills, indent=2)}")
        if self.subagents:
            import json
            parts.append(f"## Subagents\n\n{json.dumps(self.subagents, indent=2)}")
        if self.raw_config:
            parts.append(f"## Raw Configuration\n\n{self.raw_config}")
        return "\n\n---\n\n".join(parts) if parts else "(empty configuration)"
