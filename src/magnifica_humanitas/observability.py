"""Logfire instrumentation. Call configure() once at process startup."""
from __future__ import annotations

import logfire


def configure(service_name: str = "magnifica-humanitas") -> None:
    logfire.configure(service_name=service_name)
    logfire.instrument_anthropic()


def judge_span(config_description: str):
    """Context manager for a single judge invocation."""
    return logfire.span(
        "magnifica_judge",
        config_description=config_description,
    )
