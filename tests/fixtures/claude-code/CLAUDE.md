# Project context for a hypothetical SaaS app
# This file is the system prompt equivalent for Claude Code.

You are working on a Python/FastAPI web application with a PostgreSQL database.

## Repository structure

- `src/` — application source code
- `tests/` — pytest test suite
- `migrations/` — Alembic migration files

## Key constraints

- Never modify migration files directly; always generate new ones with `alembic revision`.
- The test database is separate from production; never run destructive commands against production.
- All PRs require at least one reviewer before merging.

## Development workflow

1. Write tests before implementation.
2. Run `make lint` and `make test` before committing.
3. Open a PR for any change larger than a single-line fix.
