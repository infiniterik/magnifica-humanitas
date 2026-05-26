"""Tests for all config loaders using the fixtures in tests/fixtures/."""
from __future__ import annotations

from pathlib import Path

import pytest

from magnifica_humanitas.loaders import (
    ClaudeCodeLoader,
    CodexLoader,
    OpenCodeLoader,
    AgentsFolderLoader,
    detect,
    load,
    available_loaders,
)
from magnifica_humanitas.models import AgentConfig

FIXTURES = Path(__file__).parent / "fixtures"


# ─── Detection ───────────────────────────────────────────────────────────────

class TestDetection:
    def test_claude_code_detected(self):
        assert ClaudeCodeLoader().detect(FIXTURES / "claude-code")

    def test_opencode_detected(self):
        assert OpenCodeLoader().detect(FIXTURES / "opencode")

    def test_codex_detected(self):
        assert CodexLoader().detect(FIXTURES / "codex")

    def test_agents_folder_detected(self):
        assert AgentsFolderLoader().detect(FIXTURES / "agents-dir")

    def test_auto_detect_claude_code(self):
        loader = detect(FIXTURES / "claude-code")
        assert loader is not None
        assert loader.framework_name == "claude-code"

    def test_auto_detect_opencode(self):
        loader = detect(FIXTURES / "opencode")
        assert loader is not None
        assert loader.framework_name == "opencode"

    def test_auto_detect_codex(self):
        loader = detect(FIXTURES / "codex")
        assert loader is not None
        assert loader.framework_name == "codex"

    def test_auto_detect_agents_folder(self):
        loader = detect(FIXTURES / "agents-dir")
        assert loader is not None
        assert loader.framework_name == "agents-folder"

    def test_no_detection_on_empty_dir(self, tmp_path):
        assert detect(tmp_path) is None

    def test_load_raises_on_missing_path(self):
        with pytest.raises(FileNotFoundError):
            load(Path("/nonexistent/path"))

    def test_load_raises_on_unrecognized(self, tmp_path):
        with pytest.raises(ValueError, match="No recognized"):
            load(tmp_path)

    def test_available_loaders_lists_all(self):
        names = available_loaders()
        assert "claude-code" in names
        assert "opencode" in names
        assert "codex" in names
        assert "agents-folder" in names


# ─── Claude Code loader ───────────────────────────────────────────────────────

class TestClaudeCodeLoader:
    @pytest.fixture
    def config(self) -> AgentConfig:
        return ClaudeCodeLoader().load(FIXTURES / "claude-code")

    def test_source_set(self, config):
        assert config.source == "claude-code"

    def test_system_prompt_loaded(self, config):
        assert config.system_prompt is not None
        assert "Python/FastAPI" in config.system_prompt

    def test_mcps_extracted(self, config):
        assert config.mcps is not None
        names = {m["name"] for m in config.mcps}
        assert "github" in names
        assert "filesystem" in names

    def test_skills_loaded(self, config):
        assert config.skills is not None
        assert any(s["name"] == "my-skill" for s in config.skills)
        skill = next(s for s in config.skills if s["name"] == "my-skill")
        assert "migration" in skill["content"].lower()

    def test_hooks_as_subagents(self, config):
        # The fixture has PreToolUse and Stop hooks
        assert config.subagents is not None
        names = [a["name"] for a in config.subagents]
        assert any("hook:" in n for n in names)

    def test_permissions_in_raw_config(self, config):
        assert config.raw_config is not None
        assert "allow" in config.raw_config or "deny" in config.raw_config

    def test_to_text_includes_all_sections(self, config):
        text = config.to_text()
        assert "System Prompt" in text
        assert "MCP Servers" in text
        assert "Skills" in text

    def test_mcp_command_in_description(self, config):
        github_mcp = next(m for m in config.mcps if m["name"] == "github")
        assert github_mcp["description"] is not None
        assert "npx" in github_mcp["description"]


# ─── Codex loader ─────────────────────────────────────────────────────────────

class TestCodexLoader:
    @pytest.fixture
    def config(self) -> AgentConfig:
        return CodexLoader().load(FIXTURES / "codex")

    def test_source_set(self, config):
        assert config.source == "codex"

    def test_system_prompt_from_agents_md(self, config):
        assert config.system_prompt is not None
        assert "TypeScript" in config.system_prompt

    def test_shell_tool_present(self, config):
        assert config.mcps is not None
        names = {m["name"] for m in config.mcps}
        assert "codex-shell" in names

    def test_mcp_servers_from_toml(self, config):
        names = {m["name"] for m in config.mcps}
        assert "github" in names

    def test_approval_policy_in_raw(self, config):
        assert config.raw_config is not None
        assert "approval_policy" in config.raw_config or "Approval" in config.raw_config

    def test_on_request_policy_gated(self, config):
        shell = next(m for m in config.mcps if m["name"] == "codex-shell")
        # on-request → partial gating (truthy)
        assert shell["confirmation_required"] is not False

    def test_github_mcp_confirmation(self, config):
        github = next(m for m in config.mcps if m["name"] == "github")
        # default_tools_approval_mode=prompt → confirmation_required=True
        assert github["confirmation_required"] is True


# ─── OpenCode loader ──────────────────────────────────────────────────────────

class TestOpenCodeLoader:
    @pytest.fixture
    def config(self) -> AgentConfig:
        return OpenCodeLoader().load(FIXTURES / "opencode")

    def test_source_set(self, config):
        assert config.source == "opencode"

    def test_mcps_loaded(self, config):
        assert config.mcps is not None
        names = {m["name"] for m in config.mcps}
        assert "filesystem" in names

    def test_subagents_from_agent_section(self, config):
        assert config.subagents is not None
        names = {a["name"] for a in config.subagents}
        assert "agent:researcher" in names

    def test_researcher_agent_bounded(self, config):
        researcher = next(a for a in config.subagents if "researcher" in a["name"])
        # researcher has bash:deny → should be treated as bounded/gated
        assert researcher["confirmation_required"] is True

    def test_permission_in_raw_config(self, config):
        assert config.raw_config is not None
        assert "permission" in config.raw_config.lower()

    def test_model_in_raw_config(self, config):
        assert config.raw_config is not None
        assert "claude" in config.raw_config.lower()

    def test_share_manual_not_flagged(self, config):
        # share=manual should NOT appear as a privacy concern
        assert config.raw_config is None or "PRIVACY CONCERN" not in config.raw_config


# ─── AgentsFolder loader ──────────────────────────────────────────────────────

class TestAgentsFolderLoader:
    @pytest.fixture
    def config(self) -> AgentConfig:
        return AgentsFolderLoader().load(FIXTURES / "agents-dir")

    def test_source_set(self, config):
        assert config.source == "agents-folder"

    def test_system_prompt_from_agents_md(self, config):
        assert config.system_prompt is not None
        assert "TypeScript" in config.system_prompt or "monorepo" in config.system_prompt

    def test_skills_loaded(self, config):
        assert config.skills is not None
        assert any("migration" in s["name"] for s in config.skills)

    def test_mode_as_subagent(self, config):
        assert config.subagents is not None
        names = {a["name"] for a in config.subagents}
        assert any("mode:" in n for n in names)

    def test_policy_in_raw_config(self, config):
        assert config.raw_config is not None
        assert "cautious" in config.raw_config.lower()

    def test_deny_rules_in_raw(self, config):
        assert config.raw_config is not None
        assert "DENY" in config.raw_config or "deny" in config.raw_config


# ─── AgentConfig integration ─────────────────────────────────────────────────

class TestAgentConfigIntegration:
    def test_parsed_mcps_with_confession(self):
        config = AgentConfig(
            mcps=[{"name": "db", "confession": "drop_table is ungated."}]
        )
        mcps = config.parsed_mcps()
        assert mcps[0].confession is not None
        assert "drop_table" in mcps[0].confession.acknowledgment

    def test_source_preserved_in_to_text(self):
        config = AgentConfig(
            source="claude-code",
            source_path="/workspace/project",
            system_prompt="You are helpful.",
        )
        text = config.to_text()
        assert "System Prompt" in text
        # source/source_path are metadata, not included in to_text

    @pytest.mark.parametrize("fixture,expected_source", [
        ("claude-code", "claude-code"),
        ("codex", "codex"),
        ("opencode", "opencode"),
        ("agents-dir", "agents-folder"),
    ])
    def test_all_fixtures_load_cleanly(self, fixture, expected_source):
        config = load(FIXTURES / fixture)
        assert isinstance(config, AgentConfig)
        assert config.source == expected_source
        # Every loaded config should produce non-empty to_text
        assert config.to_text() != "(empty configuration)"
