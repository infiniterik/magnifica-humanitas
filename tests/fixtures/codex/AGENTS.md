# Codex agent instructions

You are a coding assistant for a TypeScript monorepo.

## Allowed actions

- Read any file in the repository.
- Write to `src/`, `tests/`, and config files at the root.
- Run `npm test`, `npm run lint`, and `npm run build`.
- Open pull requests on GitHub.

## Prohibited actions

- Never commit directly to `main` or `release/*` branches.
- Never modify `.github/workflows/` files.
- Never install new dependencies without asking the user first.

## Style

Follow the existing code style. If unsure, ask rather than guess.
