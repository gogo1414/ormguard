# CLAUDE.md

Guidance for Claude Code (and other AI assistants) working in this repo.

## What ormguard is

Fail-fast schema validation for SQLAlchemy — the equivalent of Hibernate's
`hibernate.ddl-auto=validate`. At startup (or in CI) it reflects the connected
database and checks that it matches the ORM entities, catching entity↔DB drift
at boot instead of as a runtime `column does not exist` error.

## Commands

```bash
python -m pip install -e ".[dev]"   # setup
pytest                               # unit tests (SQLite, no external DB)
ruff check .                         # lint (line-length 110)
python -m ormguard --selfcheck       # self-contained end-to-end demo
pytest -m postgres                   # integration tests (needs DATABASE_URL)
```

## Layout

- `ormguard/core.py` — `validate()` / `assert_schema()` orchestration.
- `ormguard/reflect.py` — reflect the live DB schema.
- `ormguard/orm.py`, `ormguard/model.py` — read ORM metadata; `Finding`,
  `Severity`, `ValidationReport`, `SchemaValidationError`.
- `ormguard/diff.py` — compare reflected schema vs ORM, produce findings.
- `ormguard/config.py` — `Config` (schemas, ignores, severity toggles).
- `ormguard/cli.py` — `python -m ormguard` argument parsing.
- `ormguard/selfcheck.py` — in-memory SQLite demo with deliberate drift.
- `ormguard/integrations/` — framework hooks (e.g. FastAPI lifespan).
- `tests/` — SQLite by default; `@pytest.mark.postgres` for real Postgres.
- `docs/` — DESIGN.md, USAGE.md, V2_OFFLINE_REPLAY.md.

## Conventions

- Public API is what `ormguard/__init__.py` exports — keep it stable; note
  breaking changes in `CHANGELOG.md`.
- Support SQLAlchemy >= 1.4 and Python 3.9–3.12 (the CI matrix).
- Type/dialect comparisons are dialect-sensitive — keep `type_mismatch` opt-in.
- Version is derived from git tags via `hatch-vcs`; never hardcode a version.
- Work on a branch and open a PR; do not push to `main` directly.
- Add tests for behavior changes; `pytest` and `ruff check .` must pass.
