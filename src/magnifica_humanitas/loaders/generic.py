"""Loader for the .agents/ directory specification (agentsfolder/spec).

Directory structure:
  .agents/
    manifest.yaml      — spec version, defaults, enabled items
    modes/             — YAML files defining autonomy levels
    policies/          — YAML files defining allow/deny rules
    skills/*/          — skill definitions (SKILL.yaml or SKILL.md)
    prompts/           — instruction text files

Also handles AGENTS.md at the project root (Linux Foundation standard).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .base import ConfigLoader
from ..models import AgentConfig


def _load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return {}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _skill_from_dir(skill_dir: Path) -> dict | None:
    """Read a skill from a SKILL.yaml or SKILL.md file."""
    for fname in ["SKILL.yaml", "SKILL.yml", "SKILL.md"]:
        p = skill_dir / fname
        if not p.exists():
            continue
        content = p.read_text().strip()
        if fname.endswith((".yaml", ".yml")):
            data = _load_yaml(p)
            return {
                "name": data.get("name", skill_dir.name),
                "content": data.get("instructions") or content,
                "description": data.get("description"),
                "triggers": data.get("triggers"),
                "escalate_when": data.get("escalate_when"),
            }
        return {"name": skill_dir.name, "content": content}
    return None


def _mode_as_subagent(name: str, defn: dict) -> dict:
    """Translate a mode definition into a subagent-like entry."""
    autonomy = defn.get("autonomy", "unknown")
    confirmation = defn.get("confirmation_required", {})
    ungated = (
        autonomy in {"fully-autonomous", "autonomous"}
        or (isinstance(confirmation, dict) and all(v is False for v in confirmation.values()))
        or confirmation is False
    )
    return {
        "name": f"mode:{name}",
        "description": defn.get("description", f".agents mode: {name}"),
        "autonomy": autonomy,
        "confirmation_required": not ungated,
        "confirmation_detail": confirmation if isinstance(confirmation, dict) else None,
    }


def _policy_summary(name: str, defn: dict) -> str:
    rules = defn.get("rules", [])
    lines = [f"## Policy: {name}"]
    if defn.get("description"):
        lines.append(defn["description"])
    for rule in rules:
        action = rule.get("action", "?")
        desc = rule.get("description", rule.get("id", ""))
        lines.append(f"  [{action.upper()}] {desc}")
    return "\n".join(lines)


class AgentsFolderLoader(ConfigLoader):
    framework_name = "agents-folder"

    def detect(self, path: Path) -> bool:
        return (path / ".agents").exists() or (path / "AGENTS.md").exists()

    def load(self, path: Path) -> AgentConfig:
        agents_dir = path / ".agents"

        # Manifest
        manifest = _load_yaml(agents_dir / "manifest.yaml") if agents_dir.exists() else {}
        defaults = manifest.get("defaults", {})

        # System prompt from prompts/ directory or AGENTS.md
        system_prompt: str | None = None
        prompts_dir = agents_dir / "prompts" if agents_dir.exists() else None
        if prompts_dir and prompts_dir.exists():
            prompt_parts = [
                p.read_text().strip()
                for p in sorted(prompts_dir.glob("*.md"))
                if p.stat().st_size > 0
            ]
            if prompt_parts:
                system_prompt = "\n\n---\n\n".join(prompt_parts)
        if not system_prompt:
            for candidate in [path / "AGENTS.md", path / "TEAM_GUIDE.md", path / ".agents.md"]:
                if candidate.exists():
                    system_prompt = candidate.read_text().strip() or None
                    break

        # Skills
        skills: list[dict] = []
        if agents_dir.exists():
            for skill_dir in sorted((agents_dir / "skills").glob("*/")) if (agents_dir / "skills").exists() else []:
                s = _skill_from_dir(skill_dir)
                if s:
                    skills.append(s)

        # Modes → subagents (modes define autonomy levels)
        subagents: list[dict] = []
        if agents_dir.exists():
            modes_dir = agents_dir / "modes"
            if modes_dir.exists():
                for mode_file in sorted(modes_dir.glob("*.yaml")):
                    mode_def = _load_yaml(mode_file)
                    name = mode_def.get("name", mode_file.stem)
                    subagents.append(_mode_as_subagent(name, mode_def))

        # Policies → raw_config
        raw_parts: list[str] = []
        if agents_dir.exists():
            policies_dir = agents_dir / "policies"
            if policies_dir.exists():
                for policy_file in sorted(policies_dir.glob("*.yaml")):
                    policy_def = _load_yaml(policy_file)
                    name = policy_def.get("name", policy_file.stem)
                    raw_parts.append(_policy_summary(name, policy_def))

        # Manifest metadata
        if manifest:
            enabled = manifest.get("enabled", {})
            if enabled:
                raw_parts.append(
                    "## Enabled items\n"
                    + json.dumps(enabled, indent=2)
                )
            resolution = manifest.get("resolution", {})
            if resolution.get("denyOverridesAllow"):
                raw_parts.append(
                    "## resolution.denyOverridesAllow=true\n"
                    "Deny rules take precedence over allow rules when both match."
                )

        return AgentConfig(
            source=self.framework_name,
            source_path=str(path),
            system_prompt=system_prompt,
            mcps=None,
            skills=skills or None,
            subagents=subagents or None,
            raw_config="\n\n".join(raw_parts) or None,
        )
