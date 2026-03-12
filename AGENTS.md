# AGENTS.md

Repository guidance for coding agents working in `peewee-migrate`.

## Scope

- Applies to the whole repository.
- Prefer minimal, targeted changes over broad refactors.
- Keep behavior stable unless the task explicitly asks for behavior changes.

## Project Snapshot

- Language: Python (`>=3.10,<4`).
- Package manager and runner: `uv`.
- Main package: `peewee_migrate/`.
- Tests: `tests/` with `pytest`.
- Lint/format: `ruff`.
- Type checks: `pyrefly`.
- CLI entrypoints: `pw_migrate`, `pw-migrate`.

## Setup Commands

- Install/update env: `uv sync`.
- Install with lockfile and dev deps (CI style): `uv sync --locked --all-extras --dev`.
- Install pre-commit hooks: `uv run pre-commit install`.
- One-shot bootstrap via Make: `make` (creates `.venv` marker target).

## Build Commands

- There is no dedicated compile step for this pure-Python package.
- Packaging backend is `uv_build` (see `pyproject.toml`).
- Optional sanity check before release: `uv lock`.

## Lint / Format / Type Commands

- Format: `uv run ruff format`.
- Lint: `uv run ruff check`.
- Type check: `uv run pyrefly check`.
- Full lint gate (Make): `make lint` (runs `make types` + `ruff check`).
- Types only (Make): `make types`.

## Test Commands

- Run all tests: `uv run pytest`.
- Run all tests (Make): `make test`.
- Verbose default comes from config (`-svx` in `pyproject.toml`).

### Single-Test Execution (important)

- Single test file: `uv run pytest tests/test_router.py`.
- Single test function: `uv run pytest tests/test_router.py::test_router`.
- Single test class/method style node id: `uv run pytest path/to_file.py::TestClass::test_name`.
- Filter by keyword: `uv run pytest -k "router and not merge"`.
- Stop after first failure: `uv run pytest -x tests/test_router.py::test_router`.

## Pre-commit and Commit Rules

- Pre-commit is enforced with `fail_fast: true`.
- Hooks include:
  - `ruff format`
  - `ruff check`
  - `pyrefly check`
  - `uv-lock --check`
  - `pytest` on pre-push
  - conventional commit message validation
- Commit message convention is configured in `.git-commits.yaml`.
- Allowed commit types: `feat`, `fix`, `perf`, `refactor`, `style`, `test`, `build`, `ops`, `docs`, `merge`.

## CI Parity Commands

To mirror CI locally, run:

1. `uv sync --locked --all-extras --dev`
2. `uv run pyrefly check`
3. `uv run ruff check`
4. `uv run pytest`

## Code Style Guidelines

### General Design

- Keep functions focused and small (single responsibility).
- Prefer guard clauses and early returns over deeply nested conditionals.
- Preserve existing public APIs unless explicitly requested.
- Avoid speculative abstraction; follow existing module boundaries.

### Imports

- Use `from __future__ import annotations` at top of Python modules.
- Import order:
  1. standard library
  2. third-party packages
  3. local package imports
- Keep one blank line between import groups.
- Keep established aliases where already used:
  - `import peewee as pw`
  - `import playhouse.postgres_ext as pw_pext` (migration template context)

### Formatting

- Use Ruff formatting defaults and a max line length of 100.
- Do not hand-format against Ruff; run formatter when touching style-sensitive blocks.
- Keep trailing whitespace and EOF clean (pre-commit enforces this).

### Typing

- Add type hints for new/changed function signatures.
- Prefer built-in generics (`list[str]`, `dict[str, Any]`).
- Reuse shared aliases from `peewee_migrate/types.py` where appropriate.
- Use `TYPE_CHECKING` imports for typing-only dependencies.
- Keep type-ignore usage narrow and justified.

### Naming Conventions

- Follow existing repository conventions (not strict PEP8 naming lint; `N` rules are ignored in Ruff).
- Use descriptive snake_case for functions/variables.
- Use PascalCase for classes.
- Keep migration names meaningful and stable; router compiles them as `NNN_name.py`.

### Error Handling and Logging

- Raise explicit exceptions with actionable messages (`TypeError`, `ValueError`, `RuntimeError`).
- Prefer fail-fast validation in constructors and command entrypoints.
- Log operational context with `logger` before re-raising when needed.
- In transactional flows, preserve rollback behavior patterns already used in router/migrator.

### Testing Conventions

- Use `pytest` with plain `assert` statements.
- Keep tests close to behavior under change; extend existing test modules when possible.
- For CLI behavior, follow `click.testing.CliRunner` patterns in `tests/test_cli.py`.
- For migration behavior, prefer deterministic assertions on router `todo/done/diff` state.

### Database and Migration Safety

- Maintain compatibility across sqlite/postgresql/mysql migrator paths.
- Do not break fake migration mode (`fake=True`) behavior.
- Keep migration file generation compatible with `peewee_migrate/template.py`.
- Ensure schema-affecting changes are covered by tests.

## File/Module Layout Guidance

- Core logic lives in:
  - `peewee_migrate/migrator.py`
  - `peewee_migrate/router.py`
  - `peewee_migrate/auto.py`
- CLI surface lives in `peewee_migrate/cli.py`.
- Shared lightweight types live in `peewee_migrate/types.py`.
- Tests and migration fixtures live under `tests/`.

## Cursor / Copilot Rules Check

- Checked for `.cursor/rules/`: not present.
- Checked for `.cursorrules`: not present.
- Checked for `.github/copilot-instructions.md`: not present.
- If these files are added later, update this document and treat them as higher-priority, tool-specific instructions.

## Agent Execution Notes

- Before finalizing, run targeted tests for changed code, then run broader checks when feasible.
- Prefer `uv run ...` commands to ensure the project environment is used.
- Keep diffs minimal and avoid unrelated formatting churn.
