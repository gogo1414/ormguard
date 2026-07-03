# ormguard — Coding Conventions

Source of truth for contributors *and* the automated reviewer (CodeRabbit reads
this file via `knowledge_base.code_guidelines` in `.coderabbit.yaml`). Keep it
short and enforceable.

## Language & style

- Every module starts with `from __future__ import annotations`.
- Full type hints on public functions and dataclasses.
- `ruff check .` must pass (line length 110). No new lint ignores without reason.
- Prose docstrings on public functions/classes; explain *why*, not just *what*.

## Dependencies

- The **core** package depends only on **SQLAlchemy** (plus the Python standard
  library). Do not add third-party runtime deps to the core.
- Optional features live behind extras (e.g. `replay` → `alembic`,
  notifications → stdlib only). Guard their imports so the core still imports
  without the extra installed.

## Public API

- `ormguard/__init__.py` is the stable surface. Don't break or remove exports;
  additions are fine. Update `__all__` when you add one.

## Drift checks (the heart of the tool)

- **Low false positives over completeness.** A noisy check is worse than a
  missing one.
- Severity policy:
  - Presence problems (`table_missing`, `column_missing`) → **ERROR** (these
    crash at runtime).
  - Structural nuances (`nullable_mismatch`, `column_extra`, `type_mismatch`,
    `index_*`, `fk_*`, `default_*`) → **WARN**.
  - Anything dialect-dependent (types, indexes, FKs, server defaults) must be
    **opt-in** — a `Config` flag defaulting to `False`.
- Adding a new drift kind requires all three, together:
  1. a string constant in `ormguard/model.py` (e.g. `X_MISSING = "x_missing"`),
  2. a default severity in `ormguard/config.py` `severity_overrides`,
  3. the comparison in `ormguard/diff.py` (or the relevant reflector).
- Reflection only inspects tables the ORM declares — never scan the whole
  database (that reintroduces noise from `alembic_version`, ETL tables, etc.).

## CLI

- Exit code **1** when there are ERROR findings, **0** otherwise; `--warn-only`
  forces 0. Keep this contract.
- Output must be UTF-8 safe (works on legacy consoles like Windows cp949).
- A new CLI flag should mirror a `Config` toggle, not introduce parallel logic.

## v2 replay (`ormguard/replay/`)

- Replay must run **without a database**.
- `op.*` hooks mutate the in-memory `Catalog`; never execute real SQL.
- Any `op.execute` SQL that replay cannot interpret must be appended to
  `catalog.unparsed` — **never silently dropped** (silent drops create false
  "clean" reports).

## Tests

- Default `pytest` run is **self-contained**: in-memory SQLite or
  `pytest.importorskip(...)`. No network, no external services.
- Real-database tests must be marked (`@pytest.mark.postgres` / `mysql`) and
  **skip** when the required env var is absent.
- Every behavior change ships with a test.

## Changelog & commits

- User-facing changes get an entry under **Unreleased** in `CHANGELOG.md`
  (Keep a Changelog + SemVer).
- Commit and PR titles use conventional-commit style: `type(scope): summary`
  where type ∈ {feat, fix, docs, style, refactor, perf, test, build, ci,
  chore, revert}.
