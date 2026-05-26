"""Abstract base for all config loaders."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import AgentConfig


class ConfigLoader(ABC):
    """Reads a framework's native config files and returns a normalized AgentConfig."""

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Human-readable name shown in judge output."""

    @abstractmethod
    def detect(self, path: Path) -> bool:
        """Return True if this loader recognizes the config at the given path."""

    @abstractmethod
    def load(self, path: Path) -> AgentConfig:
        """Parse the config and return a normalized AgentConfig.

        Loaders translate framework-specific structures into the fields the judge
        understands:
        - system_prompt: the instruction text (CLAUDE.md, AGENTS.md, etc.)
        - mcps: tool/server definitions with permission and confirmation info
        - skills: named sets of encoded practices
        - subagents: automated agents / hooks with autonomy info
        - raw_config: anything that doesn't fit, as labeled text
        """
