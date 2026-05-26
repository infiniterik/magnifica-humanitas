# Magnifica Humanitas

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

### CLI

```bash
# Judge a single config (YAML or JSON)
export ANTHROPIC_API_KEY=sk-...
mh-judge judge path/to/agent-config.yaml

# Run the pydantic-evals suite
export LOGFIRE_TOKEN=...
mh-judge eval
```

### Python

```python
from magnifica_humanitas import judge, AgentConfig

config = AgentConfig(
    system_prompt="You are a pair-programming assistant...",
    mcps=[{"name": "github-read", "permissions": "read"}],
)
output = judge(config)

print(output.overall_paradigm)          # "Nehemiah", "Mixed", or "Babel"
print(output.dimension_scores["human_primacy"].score)  # 1–5
```

### Claude Code Skill

In a Claude Code session, invoke `/magnifica-judge` and paste the configuration
when prompted.

## Config format

```yaml
system_prompt: |
  You are an agent. Your job is...

mcps:
  - name: github-read
    permissions: read
    tools: [get_file_contents, list_pull_requests]
    confirmation_required: false

skills:
  - name: code-review
    content: |
      When reviewing code, raise only findings you are confident about...

subagents:
  - name: test-runner
    autonomy: bounded
    allowed_tools: [run_tests]
    can_modify_files: false
```

Pass `raw_config` as a string if the config doesn't fit the structured fields.

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
