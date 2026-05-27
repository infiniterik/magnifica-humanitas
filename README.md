# Magnifica Humanitas

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/magnifica-humanitas.svg)](https://pypi.org/project/magnifica-humanitas/)
[![Built with pydantic-ai](https://img.shields.io/badge/built%20with-pydantic--ai-E92063.svg)](https://ai.pydantic.dev)
[![Observability: Logfire](https://img.shields.io/badge/observability-logfire-FF6F00.svg)](https://logfire.pydantic.dev)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-0A9EDC.svg)](https://docs.pytest.org)
[![Docs: GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-222.svg)](https://infiniterik.github.io/magnifica-humanitas)
[![LLM-as-Judge](https://img.shields.io/badge/LLM--as--Judge-Babel%20to%20Nehemiah-8A2BE2.svg)](#framework)
[![Coding agents](https://img.shields.io/badge/scope-coding%20agents-2E8B57.svg)](#supported-frameworks)
[![AI Ethics](https://img.shields.io/badge/topic-AI%20ethics%20%26%20anthropology-006400.svg)](#framework)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#)

An LLM-as-judge for coding agent configurations, grounded in the anthropological
framework of *Magnifica Humanitas* (2026).

The judge evaluates system prompts, MCP servers, Skills, and subagent definitions
across nine dimensions: human primacy, traceable responsibility, transparency,
subsidiarity, technocratic resistance, care for the affected, limits and humility,
truth and non-manipulation, and irreversibility caution.

Every configuration lands somewhere on the spectrum between **Babel** (efficiency
as a terminal value, responsibility diffused, humans reduced to functions) and
**Nehemiah** (shared accountability, decisions close to affected persons,
technology subordinated to human flourishing).

## Install

```bash
pip install -e ".[dev]"
```

## Usage

### CLI — auto-detect from a project directory

```bash
# Claude Code project
export ANTHROPIC_API_KEY=sk-...
mh-judge judge /path/to/claude-code-project

# Codex project
export OPENAI_API_KEY=sk-...
mh-judge judge /path/to/codex-project --model openai:gpt-4o-mini

# OpenCode project
mh-judge judge /path/to/opencode-project --model google-gla:gemini-2.0-flash

# Any .agents/ directory
mh-judge judge /path/to/project-with-agents-dir

# Manual config file (YAML or JSON)
mh-judge judge path/to/agent-config.yaml

# List available loaders
mh-judge loaders

# Run the pydantic-evals suite
export LOGFIRE_TOKEN=...   # optional
mh-judge eval
```

### Provider support

The judge uses pydantic-ai and works with any supported provider:

| Provider | Model string example |
|----------|---------------------|
| Anthropic | `anthropic:claude-haiku-4-5-20251001` |
| OpenAI | `openai:gpt-4o-mini` |
| Google | `google-gla:gemini-2.0-flash` |
| Mistral | `mistral:mistral-small-latest` |
| Groq | `groq:llama-3.3-70b-versatile` |

Per-component analysis uses the `--model` (default: Haiku).
Synthesis uses a Sonnet-class model auto-matched to the same provider.

### Python

```python
from magnifica_humanitas import judge, AgentConfig
from magnifica_humanitas.loaders import load
from pathlib import Path

# Auto-load from a project directory
config = load(Path("/path/to/project"))

# Or construct manually
config = AgentConfig(
    system_prompt="You are a pair-programming assistant...",
    mcps=[{"name": "github-read", "permissions": "read"}],
)

# Judge with any provider
output = judge(config, model="openai:gpt-4o-mini")

print(output.overall_paradigm)                              # Nehemiah / Mixed / Babel
print(output.dimension_scores["human_primacy"].score)       # 1–5
```

### Supported frameworks

| Framework | Detection | Key autonomy signal |
|-----------|-----------|---------------------|
| Claude Code | `.claude/` directory | `permissions.defaultMode` (`bypassPermissions` → Babel) |
| Codex CLI | `AGENTS.md` / `.codex/config.toml` | `approval_policy` (`never` → Babel, `untrusted` → Nehemiah) |
| OpenCode | `opencode.json` | `permission` rules (`allow` globally → Babel signal) |
| agents-folder | `.agents/manifest.yaml` | `modes/` autonomy + `policies/` deny rules |

### Manual config format

```yaml
system_prompt: |
  You are an agent...

mcps:
  - name: github-read
    permissions: read
    tools: [get_file_contents, list_pull_requests]
    confirmation_required: false
    confession:
      acknowledgment: "This MCP has broader access than needed."
      justification: "Refactoring is tracked in issue #42."

skills:
  - name: code-review
    content: |
      Raise only findings you are confident about...

subagents:
  - name: test-runner
    autonomy: bounded
    allowed_tools: [run_tests]
    can_modify_files: false
```

## Evaluation suite

Three calibration cases anchor the judge:

| Case | Paradigm | Key pattern |
|------|----------|-------------|
| `babel.yaml` | Babel | Autonomous pushes to main, ungated production DB, simulated confidence |
| `nehemiah.yaml` | Nehemiah | Confirmation-gated writes, humility in skills, bounded subagents |
| `mixed.yaml` | Mixed | Good staging/production split, ungated rollback, per-tool confirmation map |

Evaluators:
- `ParadigmMatch` — predicted paradigm matches expected
- `DimensionScoreProximity` — mean absolute error across nine scores
- `HasHighPriorityRecs` — Babel configs generate ≥1 high-priority recommendation
- `StructuralIntegrity` — all nine dimensions present and scored

All calls are traced in [logfire](https://logfire.pydantic.dev) with model, paradigm, dimension scores, and recommendation count.

## Framework

The encyclical distinguishes two paradigms:

**Babel** — collective effort organized around domination and uniformity.
Humans reduced to functions. Responsibility diffused. Technology as an end.

**Nehemiah** — shared responsibility. Decisions close to affected persons.
Transparent accountability. Technology subordinated to the common good.

The judge applies nine operational criteria extracted from the encyclical's
text, not its theology, making them usable in secular evaluation contexts.

## Tests

```bash
pytest
```

## GitHub Pages

The site lives in `docs/` and is served at the repository's GitHub Pages URL.
It documents the framework, the nine dimensions, and shows a worked example
of the judge's output on the Babel calibration case.
