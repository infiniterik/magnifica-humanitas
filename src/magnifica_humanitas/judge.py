"""Core judge: sends an AgentConfig to Claude and returns a structured JudgeOutput."""
from __future__ import annotations

import json
from pathlib import Path

import anthropic
import logfire

from .models import AgentConfig, JudgeOutput

_SKILL_DIR = Path(__file__).parent.parent.parent / ".claude" / "skills" / "magnifica-judge"
_JUDGE_PROMPT_PATH = _SKILL_DIR / "judge_prompt.md"

# Loaded once at import time so the file is not re-read per call.
_JUDGE_SYSTEM_PROMPT: str | None = None


def _load_system_prompt() -> str:
    global _JUDGE_SYSTEM_PROMPT
    if _JUDGE_SYSTEM_PROMPT is None:
        _JUDGE_SYSTEM_PROMPT = _JUDGE_PROMPT_PATH.read_text()
    return _JUDGE_SYSTEM_PROMPT


def _make_user_message(config: AgentConfig) -> str:
    return (
        "Please analyze the following coding agent configuration using the "
        "Magnifica Humanitas framework. Return ONLY valid JSON matching the "
        "specified schema — no prose before or after.\n\n"
        "<configuration>\n"
        + config.to_text()
        + "\n</configuration>"
    )


@logfire.instrument("judge_config", extract_args=True)
def judge(
    config: AgentConfig,
    *,
    model: str = "claude-opus-4-7-20251101",
    client: anthropic.Anthropic | None = None,
) -> JudgeOutput:
    """Run the Magnifica Humanitas judge on a coding agent config.

    Args:
        config: The agent configuration to evaluate.
        model: Claude model to use.  Defaults to Opus for reasoning depth.
        client: Optional pre-configured Anthropic client (for testing/injection).
    """
    if client is None:
        client = anthropic.Anthropic()

    system_prompt = _load_system_prompt()

    with logfire.span("anthropic_call", model=model):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": _make_user_message(config)}],
        )

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if the model wraps in ```json ... ```
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        raw_text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    parsed = json.loads(raw_text)
    output = JudgeOutput.model_validate(parsed)

    logfire.info(
        "judge_complete",
        paradigm=output.overall_paradigm,
        babel_count=len(output.babel_indicators),
        nehemiah_count=len(output.nehemiah_indicators),
        high_priority_recs=sum(
            1 for r in output.recommendations if r.priority == "high"
        ),
    )

    return output
