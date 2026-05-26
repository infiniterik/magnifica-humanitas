"""Auto-detect and load an agent configuration from a directory."""
from __future__ import annotations

from pathlib import Path

from .base import ConfigLoader
from .claude_code import ClaudeCodeLoader
from .codex import CodexLoader
from .opencode import OpenCodeLoader
from .generic import AgentsFolderLoader
from ..models import AgentConfig

# Detection order matters: more specific loaders come first.
_LOADERS: list[ConfigLoader] = [
    ClaudeCodeLoader(),
    OpenCodeLoader(),
    CodexLoader(),
    AgentsFolderLoader(),
]


def detect(path: Path) -> ConfigLoader | None:
    """Return the first loader that recognizes the config at *path*, or None."""
    for loader in _LOADERS:
        if loader.detect(path):
            return loader
    return None


def load(path: Path) -> AgentConfig:
    """Auto-detect and load an agent configuration from a directory.

    Raises FileNotFoundError if the path doesn't exist.
    Raises ValueError if no loader recognizes the configuration.
    """
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    loader = detect(path)
    if loader is None:
        raise ValueError(
            f"No recognized agent configuration found at {path}.\n"
            f"Looked for: .claude/ (Claude Code), opencode.json (OpenCode), "
            f"AGENTS.md / codex.json (Codex), .agents/ (agents-folder spec)."
        )

    return loader.load(path)


def available_loaders() -> list[str]:
    """Return the framework names of all registered loaders."""
    return [l.framework_name for l in _LOADERS]
