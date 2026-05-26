"""Loader for Claude Code configurations.

File locations (merged in priority order, lowest to highest):
  ~/.claude/settings.json          user scope
  <project>/.claude/settings.json  project scope (team, committed)
  <project>/.claude/settings.local.json  local overrides (gitignored)

MCP servers also declared in:
  ~/.claude.json    user-level MCP config
  <project>/.mcp.json  project-level MCP config

System prompt:
  <project>/CLAUDE.md or <project>/.claude/CLAUDE.md

Skills:
  <project>/.claude/skills/*/SKILL.md

Key autonomy fields:
  permissions.defaultMode: default | acceptEdits | plan | auto | dontAsk | bypassPermissions
  permissions.allow / .deny / .ask: tool-pattern permission lists
  hooks: PreToolUse / PostToolUse / Stop shell commands
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import ConfigLoader
from ..models import AgentConfig


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _deep_merge(*dicts: dict) -> dict:
    """Last writer wins on each top-level key."""
    result: dict = {}
    for d in dicts:
        result.update(d)
    return result


# Maps defaultMode to a human-readable autonomy description
_DEFAULT_MODE_NOTES = {
    "default": "defaultMode=default: standard permission prompts apply.",
    "acceptEdits": (
        "defaultMode=acceptEdits: file edits are auto-accepted without prompting. "
        "Writes to the codebase are ungated."
    ),
    "plan": "defaultMode=plan: agent shows a plan and waits for approval before acting.",
    "auto": (
        "defaultMode=auto: agent auto-approves operations deemed safe; "
        "risky operations still prompt."
    ),
    "dontAsk": (
        "defaultMode=dontAsk: agent skips permission prompts. "
        "Equivalent to bypassPermissions for most operations."
    ),
    "bypassPermissions": (
        "defaultMode=bypassPermissions: ALL permission checks bypassed. "
        "Every tool call executes without confirmation. Highest Babel signal."
    ),
}

_UNGATED_MODES = {"acceptEdits", "dontAsk", "bypassPermissions", "auto"}


def _mcp_from_server(name: str, defn: dict) -> dict:
    command = defn.get("command", "")
    args = defn.get("args", [])
    cmd = " ".join([command] + [str(a) for a in args]) if command else None
    return {
        "name": name,
        "description": cmd,
        "tools": None,
        "permissions": defn.get("type", "stdio"),
        "confirmation_required": None,
        "env_keys": list(defn.get("env", {}).keys()) or None,
    }


def _format_permissions(permissions: dict) -> str:
    """Render allow/deny/ask arrays as labeled text."""
    if not permissions:
        return ""
    lines = ["## Claude Code permission lists"]
    for key in ("allow", "ask", "deny"):
        vals = permissions.get(key, [])
        if vals:
            lines.append(f"{key}:")
            lines.extend(f"  - {v}" for v in vals)
    mode = permissions.get("defaultMode")
    if mode:
        lines.append(f"defaultMode: {mode}")
        note = _DEFAULT_MODE_NOTES.get(mode, f"defaultMode={mode}")
        lines.append(f"  ({note})")
    auto_mode = permissions.get("autoMode")
    if auto_mode:
        lines.append(f"autoMode: {json.dumps(auto_mode)}")
    return "\n".join(lines)


def _hook_as_subagent(event: str, matcher: str | None, command: str) -> dict:
    tag = f"hook:{event}" + (f"[{matcher}]" if matcher else "")
    return {
        "name": tag,
        "description": (
            f"Shell command hook: runs '{command}' "
            + (f"before {matcher} tool calls" if event == "PreToolUse" and matcher
               else f"on {event} event")
        ),
        "autonomy": "autonomous_with_notification",
        "allowed_tools": ["shell"],
        "confirmation_required": False,
        "reports_to": "none",
    }


class ClaudeCodeLoader(ConfigLoader):
    framework_name = "claude-code"

    def detect(self, path: Path) -> bool:
        return (path / ".claude").exists()

    def load(self, path: Path) -> AgentConfig:
        claude_dir = path / ".claude"

        # Merge settings: user < project < local
        settings: dict[str, Any] = _deep_merge(
            _load_json(Path.home() / ".claude" / "settings.json"),
            _load_json(claude_dir / "settings.json"),
            _load_json(claude_dir / "settings.local.json"),
        )

        # MCPs from mcpServers in settings + .mcp.json
        mcp_servers: dict[str, Any] = {}
        mcp_servers.update(_load_json(Path.home() / ".claude.json").get("mcpServers", {}))
        mcp_servers.update(_load_json(path / ".mcp.json").get("mcpServers", {}))
        mcp_servers.update(settings.get("mcpServers", {}))
        mcps = [_mcp_from_server(n, d) for n, d in mcp_servers.items()] or None

        # Allowed / denied MCP server lists
        allowed_mcps = settings.get("allowedMcpServers", [])
        denied_mcps = settings.get("deniedMcpServers", [])

        # System prompt
        system_prompt: str | None = None
        for candidate in [path / "CLAUDE.md", claude_dir / "CLAUDE.md"]:
            if candidate.exists():
                system_prompt = candidate.read_text().strip() or None
                break

        # Skills
        skills: list[dict] | None = None
        skills_dir = claude_dir / "skills"
        if skills_dir.exists():
            found = [
                {"name": md.parent.name, "content": md.read_text().strip()}
                for md in sorted(skills_dir.glob("*/SKILL.md"))
            ]
            skills = found or None

        # Hooks → subagents
        subagents: list[dict] = []
        for event, hook_list in settings.get("hooks", {}).items():
            if not isinstance(hook_list, list):
                continue
            for entry in hook_list:
                matcher = entry.get("matcher") if isinstance(entry, dict) else None
                for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
                    cmd = hook.get("command", "")
                    if cmd:
                        subagents.append(_hook_as_subagent(event, matcher, cmd))

        # raw_config: permissions summary + model + MCP allow/deny lists
        raw_parts: list[str] = []
        perm = settings.get("permissions", {})
        perm_text = _format_permissions(perm)
        if perm_text:
            raw_parts.append(perm_text)
        if allowed_mcps:
            raw_parts.append(
                "## allowedMcpServers\n" + "\n".join(f"  - {s}" for s in allowed_mcps)
            )
        if denied_mcps:
            raw_parts.append(
                "## deniedMcpServers\n" + "\n".join(f"  - {s}" for s in denied_mcps)
            )
        model = settings.get("model")
        if model:
            raw_parts.append(f"## Model\n{model}")

        # Autonomy signal from defaultMode
        mode = perm.get("defaultMode", "")
        if mode in _UNGATED_MODES:
            raw_parts.append(
                f"## WARNING: Ungated autonomy mode\n{_DEFAULT_MODE_NOTES.get(mode, mode)}"
            )

        return AgentConfig(
            source=self.framework_name,
            source_path=str(path),
            system_prompt=system_prompt,
            mcps=mcps,
            skills=skills,
            subagents=subagents or None,
            raw_config="\n\n".join(raw_parts) or None,
        )
