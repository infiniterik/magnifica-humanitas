"""Loader for OpenAI Codex CLI configurations.

File locations (merged, lowest to highest priority):
  ~/.codex/config.toml                   user config (primary format, TOML)
  ~/.codex/config.json                   user config (JSON variant)
  <project>/.codex/config.toml           project config
  <project>/codex.json                   project config (JSON variant)

Instructions (AGENTS.md search order per spec):
  ~/.codex/AGENTS.md                     user defaults
  <project>/AGENTS.md                    project instructions
  <project>/TEAM_GUIDE.md               fallback
  <project>/.agents.md                   fallback

Key autonomy field — approval_policy:
  "never"      — never request approval; fully autonomous (Babel indicator)
  "on-request" — agent can interactively request more permissions
  "untrusted"  — treat every action as untrusted; ask before each one (Nehemiah)

MCP servers in [mcp_servers.*] with per-tool default_tools_approval_mode:
  "auto"    — no approval needed
  "prompt"  — ask before use
  "approve" — explicit pre-approval required
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import ConfigLoader
from ..models import AgentConfig

_USER_CONFIG_DIR = Path.home() / ".codex"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _load_toml(path: Path) -> dict:
    try:
        import tomllib
        return tomllib.loads(path.read_text())
    except (ImportError, AttributeError):
        pass
    try:
        import tomli  # type: ignore[import]
        return tomli.loads(path.read_text())
    except Exception:
        return {}
    except Exception:
        return {}


def _load_config(directory: Path) -> dict:
    """Try TOML first (canonical), then JSON."""
    d = _load_toml(directory / "config.toml")
    if not d:
        d = _load_json(directory / "config.json")
    # Also try inline codex.json at root
    if not d:
        d = _load_json(directory / "codex.json")
    return d


def _merge(*dicts: dict) -> dict:
    result: dict = {}
    for d in dicts:
        result.update(d)
    return result


_POLICY_NOTE = {
    "never": (
        "approval_policy=never: agent never requests approval — fully autonomous. "
        "Every shell command and file write executes without confirmation. "
        "Strongest Babel indicator in the Codex configuration surface."
    ),
    "on-request": (
        "approval_policy=on-request: agent operates interactively; "
        "it may request additional permissions during a session. "
        "Human is in the loop for elevated actions."
    ),
    "untrusted": (
        "approval_policy=untrusted: every action is treated as untrusted and "
        "requires explicit user confirmation before execution. "
        "Strongest Nehemiah indicator in the Codex configuration surface."
    ),
}

# confirmation_required: False = ungated (Babel), True = gated (Nehemiah)
_POLICY_GATED = {
    "never": False,
    "on-request": "partial",
    "untrusted": True,
}


def _mcp_from_codex(name: str, defn: dict) -> dict:
    command = defn.get("command", "")
    args = defn.get("args", [])
    cmd = " ".join([command] + [str(a) for a in args]) if command else None
    approval = defn.get("default_tools_approval_mode", "prompt")
    confirmation = approval != "auto"
    return {
        "name": name,
        "description": cmd,
        "tools": defn.get("enabled_tools"),
        "permissions": "execute",
        "confirmation_required": confirmation,
        "default_tools_approval_mode": approval,
    }


def _read_instructions(path: Path) -> str | None:
    for name in ["AGENTS.md", "TEAM_GUIDE.md", ".agents.md"]:
        candidate = path / name
        if candidate.exists():
            return candidate.read_text().strip() or None
    return None


class CodexLoader(ConfigLoader):
    framework_name = "codex"

    def detect(self, path: Path) -> bool:
        return (
            (path / "AGENTS.md").exists()
            or (path / "TEAM_GUIDE.md").exists()
            or (path / ".agents.md").exists()
            or (path / "codex.json").exists()
            or (path / ".codex" / "config.toml").exists()
            or (path / ".codex" / "config.json").exists()
        )

    def load(self, path: Path) -> AgentConfig:
        config = _merge(
            _load_config(_USER_CONFIG_DIR),
            _load_config(path / ".codex"),
            _load_json(path / "codex.json"),
        )

        # Instructions: user default + project
        user_instr = _read_instructions(_USER_CONFIG_DIR)
        project_instr = _read_instructions(path)
        inline_instr = config.get("instructions", "").strip() if isinstance(
            config.get("instructions"), str
        ) else None
        parts = [p for p in [user_instr, project_instr, inline_instr] if p]
        system_prompt = "\n\n---\n\n".join(parts) or None

        # approval_policy → MCPs with confirmation mapping
        policy = config.get("approval_policy", "on-request")
        gated = _POLICY_GATED.get(policy, "partial")
        policy_note = _POLICY_NOTE.get(policy, f"approval_policy={policy!r}")

        # Built-in shell + file tools
        shell_tool: dict = {
            "name": "codex-shell",
            "description": "Shell command execution (Codex built-in)",
            "tools": ["run_shell_command"],
            "permissions": "execute",
            "confirmation_required": gated,
            "approval_policy": policy,
        }
        file_tool: dict = {
            "name": "codex-filesystem",
            "description": "File read/write (Codex built-in)",
            "tools": ["read_file", "write_file", "list_directory"],
            "permissions": "readwrite",
            "confirmation_required": gated,
        }
        mcps: list[dict] = [shell_tool, file_tool]

        # Declared MCP servers
        for name, defn in config.get("mcp_servers", {}).items():
            mcps.append(_mcp_from_codex(name, defn))

        # raw_config
        raw_parts = [f"## Approval policy\n{policy_note}"]

        # Permissions filesystem/network
        permissions: dict[str, Any] = config.get("permissions", {})
        for pname, pdef in permissions.items():
            if isinstance(pdef, dict):
                raw_parts.append(
                    f"## Permission profile: {pname}\n"
                    + json.dumps(pdef, indent=2)
                )

        model = config.get("model")
        if model:
            raw_parts.append(f"## Model\n{config.get('model_provider', '')}:{model}")
        features: dict = config.get("features", {})
        if features:
            raw_parts.append(f"## Features\n{json.dumps(features, indent=2)}")

        return AgentConfig(
            source=self.framework_name,
            source_path=str(path),
            system_prompt=system_prompt,
            mcps=mcps,
            skills=None,
            subagents=None,
            raw_config="\n\n".join(raw_parts),
        )
