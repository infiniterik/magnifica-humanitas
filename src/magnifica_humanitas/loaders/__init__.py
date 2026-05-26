"""Config loaders for agent frameworks.

    from magnifica_humanitas.loaders import load, detect, available_loaders
    from magnifica_humanitas.loaders import ClaudeCodeLoader, CodexLoader, OpenCodeLoader, AgentsFolderLoader
"""
from .auto import load, detect, available_loaders
from .base import ConfigLoader
from .claude_code import ClaudeCodeLoader
from .codex import CodexLoader
from .opencode import OpenCodeLoader
from .generic import AgentsFolderLoader

__all__ = [
    "load",
    "detect",
    "available_loaders",
    "ConfigLoader",
    "ClaudeCodeLoader",
    "CodexLoader",
    "OpenCodeLoader",
    "AgentsFolderLoader",
]
