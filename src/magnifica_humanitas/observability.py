"""Logfire instrumentation. Call configure() once at process startup."""
from __future__ import annotations

import logfire


def configure(service_name: str = "magnifica-humanitas") -> None:
    logfire.configure(service_name=service_name)
    logfire.instrument_pydantic_ai()  # instruments all pydantic-ai Agent calls
