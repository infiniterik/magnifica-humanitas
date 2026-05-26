from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


# ─── Shared primitives ────────────────────────────────────────────────────────

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


class DimensionScore(BaseModel):
    score: Annotated[int, Field(ge=1, le=5)]
    evidence: str
    concerns: str


class Recommendation(BaseModel):
    priority: Literal["high", "medium", "low"]
    component: str
    change: str
    rationale: str


# ─── Confession ───────────────────────────────────────────────────────────────


class Confession(BaseModel):
    """An explicit acknowledgment by the config author of a known violation.

    Including a confession does not absolve the violation — it contextualizes it.
    The judge lowers recommendation priority for credible confessions but keeps
    the finding and does not improve the dimension score.
    """

    acknowledgment: str
    justification: str | None = None


# ─── Input: per-component definitions with optional confession ────────────────


class MCPDefinition(BaseModel):
    name: str
    description: str | None = None
    tools: list[str] | list[dict] | None = None
    permissions: str | None = None
    confirmation_required: bool | dict | None = None
    confession: Confession | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "MCPDefinition":
        c = d.get("confession")
        if isinstance(c, str):
            d = {**d, "confession": {"acknowledgment": c}}
        return cls.model_validate(d)


class SkillDefinition(BaseModel):
    name: str
    content: str | None = None
    confession: Confession | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "SkillDefinition":
        c = d.get("confession")
        if isinstance(c, str):
            d = {**d, "confession": {"acknowledgment": c}}
        return cls.model_validate(d)


class SubagentDefinition(BaseModel):
    name: str
    description: str | None = None
    autonomy: str | None = None
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    confirmation_required: bool | dict | None = None
    reports_to: str | None = None
    confession: Confession | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "SubagentDefinition":
        c = d.get("confession")
        if isinstance(c, str):
            d = {**d, "confession": {"acknowledgment": c}}
        return cls.model_validate(d)


class AgentConfig(BaseModel):
    """Top-level input to the judge."""

    system_prompt: str | None = None
    mcps: list[dict] | None = None
    skills: list[dict] | None = None
    subagents: list[dict] | None = None
    raw_config: str | None = None

    # Populated by loaders; ignored by manual/YAML configs
    source: str | None = None
    source_path: str | None = None

    def parsed_mcps(self) -> list[MCPDefinition]:
        return [MCPDefinition.from_dict(m) for m in (self.mcps or [])]

    def parsed_skills(self) -> list[SkillDefinition]:
        return [SkillDefinition.from_dict(s) for s in (self.skills or [])]

    def parsed_subagents(self) -> list[SubagentDefinition]:
        return [SubagentDefinition.from_dict(a) for a in (self.subagents or [])]

    def to_text(self) -> str:
        import json
        parts: list[str] = []
        if self.system_prompt:
            parts.append(f"## System Prompt\n\n{self.system_prompt}")
        if self.mcps:
            parts.append(f"## MCP Servers\n\n{json.dumps(self.mcps, indent=2)}")
        if self.skills:
            parts.append(f"## Skills\n\n{json.dumps(self.skills, indent=2)}")
        if self.subagents:
            parts.append(f"## Subagents\n\n{json.dumps(self.subagents, indent=2)}")
        if self.raw_config:
            parts.append(f"## Raw Configuration\n\n{self.raw_config}")
        return "\n\n---\n\n".join(parts) if parts else "(empty configuration)"


# ─── Intermediate outputs ─────────────────────────────────────────────────────


class ContextAssessment(BaseModel):
    operational_context: str
    blast_radius: Literal["low", "medium", "high", "critical"]
    inferred_scale: Literal["personal", "team", "organization", "public"]
    domain: str | None = None
    affected_parties: list[str]
    scale_note: str


class ComponentAnalysis(BaseModel):
    """Result of analyzing one component (system prompt / MCP / skill / subagent)."""

    component_type: Literal["system_prompt", "mcp", "skill", "subagent"]
    component_name: str
    confession_considered: str | None = None
    dimension_scores: dict[DimensionKey, DimensionScore]
    findings: list[str]
    babel_signals: list[str]
    nehemiah_signals: list[str]
    recommendations: list[Recommendation]


# ─── Final output ─────────────────────────────────────────────────────────────


class ConfessionVerdict(BaseModel):
    component_type: str
    component_name: str
    acknowledgment: str
    verdict: Literal["justified", "unjustified", "partially_justified"]
    verdict_rationale: str


class ComponentFinding(BaseModel):
    name: str
    concerns: str
    strengths: str


class JudgeOutput(BaseModel):
    overall_paradigm: Literal["Babel", "Mixed", "Nehemiah"]
    overall_summary: str
    dimension_scores: dict[DimensionKey, DimensionScore]
    component_findings: dict[
        Literal["system_prompt", "mcps", "skills", "subagents"],
        list[str] | list[ComponentFinding],
    ]
    confessions: list[ConfessionVerdict] = Field(default_factory=list)
    babel_indicators: list[str]
    nehemiah_indicators: list[str]
    recommendations: list[Recommendation]
    open_questions: list[str]
