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
pytest -m mysql                      # integration tests (needs DATABASE_URL_MYSQL)
python -m ormguard replay --migrations <dir> --metadata <mod:attr>  # v2 offline replay
```

## Layout

- `ormguard/core.py` — `validate()` / `assert_schema()` orchestration.
- `ormguard/reflect.py` — reflect the live DB schema.
- `ormguard/orm.py`, `ormguard/model.py` — read ORM metadata; `Finding`,
  `Severity`, `ValidationReport`, `SchemaValidationError`.
- `ormguard/diff.py` — compare reflected schema vs ORM, produce findings.
- `ormguard/config.py`, `ormguard/configfile.py` — `Config` (schemas, ignores,
  severity toggles) + TOML/pyproject config loading.
- `ormguard/cli.py`, `ormguard/__main__.py` — `python -m ormguard` (check,
  replay, selfcheck modes).
- `ormguard/replay/` — v2 offline Alembic replay (loader, engine, recorder,
  catalog, report, sql) — see `docs/V2_OFFLINE_REPLAY.md`.
- `ormguard/output.py` — report formats: text, json, SARIF, GitHub annotations.
- `ormguard/baseline.py` — accepted-findings baseline (`--baseline`,
  `--write-baseline`).
- `ormguard/suggest.py`, `ormguard/usage.py` — fix suggestions; usage-aware
  ranking of findings.
- `ormguard/fleet.py`, `ormguard/matrix.py` — multi-DB/tenant validation and
  divergence matrix.
- `ormguard/notify.py` — webhook notifications (stdlib only).
- `ormguard/selfcheck.py` — in-memory SQLite demo with deliberate drift.
- `ormguard/integrations/` — framework hooks (e.g. FastAPI lifespan).
- `action.yml` — GitHub Action v2 (check/replay commands, SARIF, baselines).
- `tests/` — SQLite by default; `@pytest.mark.postgres` / `@pytest.mark.mysql`
  for real DBs.
- `docs/` — DESIGN.md, USAGE.md, V2_OFFLINE_REPLAY.md, CONVENTIONS.md.

## Conventions

- **`docs/CONVENTIONS.md` is the source of truth for coding style** (CodeRabbit
  also enforces it via `.coderabbit.yaml`). Highlights: `from __future__ import
  annotations` in every module; full type hints on public surfaces; core
  package depends on SQLAlchemy only — optional features live behind extras
  with guarded imports; low false positives over completeness in drift checks.
- Public API is what `ormguard/__init__.py` exports (`__all__`) — keep it
  stable, additions only; update `__all__` and note breaking changes in
  `CHANGELOG.md`.
- Support SQLAlchemy >= 1.4 and Python 3.9–3.12 (the CI matrix).
- Type/dialect comparisons are dialect-sensitive — keep `type_mismatch` opt-in.
- Version is derived from git tags via `hatch-vcs`; never hardcode a version.
- Work on a branch and open a PR; do not push to `main` directly.
- Add tests for behavior changes; `pytest` and `ruff check .` must pass.
