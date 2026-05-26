"""Loader for OpenCode configurations.

File locations (merged, lowest to highest priority):
  ~/.config/opencode/opencode.json    user config (XDG)
  <project>/opencode.json             project config

System prompt from instructions array (resolved paths) or AGENTS.md / CLAUDE.md.

Key permission field:
  "permission": "allow|ask|deny"    — global shorthand
  OR granular per-tool dict:
  "permission": {
    "*": "ask",
    "bash": { "git *": "allow", "rm -rf *": "deny", "*": "ask" },
    "edit": "ask",
    "read": { ".env*": "deny", "*": "allow" }
  }

Agent subagents:
  "agent": {
    "researcher": {
      "model": "...",
      "prompt": "...",
      "tools": [...],
      "permission": { ... }
    }
  }

Share/privacy:
  "share": "manual|auto|disabled"
  "auto" publishes session data externally.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import ConfigLoader
from ..models import AgentConfig

_XDG = Path.home() / ".config" / "opencode"


def _load_json(path: Path) -> dict:
    try:
        text = path.read_text()
        # Strip line comments for JSONC
        import re
        text = re.sub(r'//[^\n]*', '', text)
        return json.loads(text)
    except (json.JSONDecodeError, OSError):
        return {}


def _load_toml(path: Path) -> dict:
    try:
        import tomllib
        return tomllib.loads(path.read_text())
    except Exception:
        try:
            import tomli  # type: ignore[import]
            return tomli.loads(path.read_text())
        except Exception:
            return {}


def _load_config(directory: Path) -> dict:
    d = _load_json(directory / "opencode.json")
    if not d:
        d = _load_toml(directory / "opencode.toml")
    return d


def _mcp_from_opencode(name: str, defn: dict) -> dict:
    command = defn.get("command", "")
    args = defn.get("args", [])
    cmd = " ".join([command] + [str(a) for a in args]) if command else defn.get("url")
    return {
        "name": name,
        "description": cmd,
        "tools": None,
        "permissions": defn.get("type", "stdio"),
        "confirmation_required": None,
        "enabled": defn.get("enabled", True),
    }


def _permission_summary(permission: Any) -> str:
    """Render permission field (string or dict) as labeled text."""
    if isinstance(permission, str):
        labels = {
            "allow": "All tools execute without confirmation (Babel indicator if broad).",
            "ask": "All tools require confirmation before execution.",
            "deny": "All tool use denied.",
        }
        return f"## Global permission: {permission}\n{labels.get(permission, '')}"
    if isinstance(permission, dict):
        lines = ["## Per-tool permission rules"]
        for tool, rule in permission.items():
            if isinstance(rule, str):
                lines.append(f"  {tool}: {rule}")
            elif isinstance(rule, dict):
                lines.append(f"  {tool}:")
                for pattern, action in rule.items():
                    lines.append(f"    {pattern!r}: {action}")
        return "\n".join(lines)
    return ""


def _subagent_from_opencode(name: str, defn: dict) -> dict:
    perm = defn.get("permission", {})
    # If any tool in the agent is "allow" without qualification, flag it
    has_ungated = (
        perm == "allow"
        or (isinstance(perm, dict) and any(v == "allow" for v in perm.values()))
    )
    return {
        "name": f"agent:{name}",
        "description": defn.get("prompt", f"OpenCode subagent: {name}"),
        "autonomy": "bounded",
        "allowed_tools": defn.get("tools", []),
        "confirmation_required": not has_ungated,
        "model": defn.get("model"),
        "permission": perm,
    }


class OpenCodeLoader(ConfigLoader):
    framework_name = "opencode"

    def detect(self, path: Path) -> bool:
        return (
            (path / "opencode.json").exists()
            or (path / "opencode.toml").exists()
        )

    def load(self, path: Path) -> AgentConfig:
        config = {**_load_config(_XDG), **_load_config(path)}

        # System prompt from instructions paths or markdown files
        system_prompt: str | None = None
        instructions_raw = config.get("instructions")
        if isinstance(instructions_raw, list):
            parts: list[str] = []
            for pattern in instructions_raw:
                for p in sorted(path.glob(pattern)):
                    if p.is_file():
                        parts.append(p.read_text().strip())
            if parts:
                system_prompt = "\n\n---\n\n".join(parts)
        if not system_prompt:
            for candidate in [path / "AGENTS.md", path / "CLAUDE.md"]:
                if candidate.exists():
                    system_prompt = candidate.read_text().strip() or None
                    break

        # MCPs
        mcps = [_mcp_from_opencode(n, d) for n, d in config.get("mcp", {}).items()] or None

        # Subagents from "agent" section
        subagents = [
            _subagent_from_opencode(n, d)
            for n, d in config.get("agent", {}).items()
        ] or None

        # raw_config
        raw_parts: list[str] = []
        perm = config.get("permission")
        if perm is not None:
            raw_parts.append(_permission_summary(perm))

        model = config.get("model")
        if model:
            raw_parts.append(f"## Model\n{model}")

        share = config.get("share")
        if share == "auto":
            raw_parts.append(
                "## share=auto (PRIVACY CONCERN)\n"
                "Sessions are published externally automatically. Codebase contents, "
                "developer queries, and any secrets in context may be shared."
            )
        elif share:
            raw_parts.append(f"## share={share}")

        tools_cfg = config.get("tools", {})
        if tools_cfg:
            disabled = [t for t, v in tools_cfg.items() if v is False]
            if disabled:
                raw_parts.append(f"## Disabled tools\n" + ", ".join(disabled))

        return AgentConfig(
            source=self.framework_name,
            source_path=str(path),
            system_prompt=system_prompt,
            mcps=mcps,
            skills=None,
            subagents=subagents,
            raw_config="\n\n".join(raw_parts) or None,
        )
