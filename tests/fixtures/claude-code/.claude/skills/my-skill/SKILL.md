# My Skill

A sample skill that reviews database migrations for safety.

## When to use

Invoke when asked to review or generate an Alembic migration file.

## Instructions

1. Check for destructive operations: `DROP TABLE`, `DROP COLUMN`, column type narrowing.
2. For each destructive operation, ask the developer to confirm before proceeding.
3. Suggest adding a `downgrade()` function if none exists.
4. Never generate a migration that removes data without explicit confirmation.
