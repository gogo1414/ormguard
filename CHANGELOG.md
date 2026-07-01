# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- CLI no longer crashes with `UnicodeEncodeError` on legacy consoles (e.g.
  Windows cp949); stdout/stderr are reconfigured to UTF-8. (#12)

### Documentation

- Added a top-of-README "Quickstart (60 seconds)" with copy-paste install,
  `--selfcheck`, FastAPI guard, and CI snippets. (#11)

### Added

- Optional enum validation (`Config(check_enums=True)`): emits `enum_mismatch`
  when an enum column's allowed values differ between the ORM and the database
  (native enums on Postgres/MySQL), naming the differing values. Opt-in, WARN,
  and skipped when either side exposes no enum values. (#5)
- Optional CHECK-constraint validation (`Config(check_constraints=True)`): emits
  `check_missing` / `check_extra`, compared by constraint *name* only (the
  expression text is dialect-rewritten on reflection, so it is not diffed);
  unnamed constraints are skipped. Opt-in, WARN. (#5)
- **v2 (offline replay), M1**: replay Alembic migrations into an in-memory
  catalog without a database and diff against ORM metadata
  (`ormguard.replay.replay_migrations` / `validate_migrations`). Hooks `op.*`
  (create/drop/alter table & column, `batch_alter_table`) and orders revisions
  by the DAG (branches/merges). Raw `op.execute` SQL is collected for a later
  milestone (M3). Adds the `replay` extra (`pip install ormguard[replay]`).
- Webhook notifications: `--notify-webhook URL` (and `--notify-on error|any`)
  POST the report to a Slack- or Discord-compatible incoming webhook when drift
  is found — one payload works for both, standard library only, best-effort.
  Also exposed as a `notify-webhook` input on the GitHub Action. (#22)
- Reusable GitHub Action (`action.yml`): run ormguard in any repo's CI with a
  few lines — inputs for `database-url`, `metadata`, extra `args`, install
  `version`, and `python-version`. (#8)
- Optional server-default validation (`Config(check_server_defaults=True)` /
  `--check-defaults`): emits `default_missing` / `default_extra` by comparing
  *presence* of a DB default (not its value, which is dialect-dependent),
  skipping primary keys. Opt-in, defaults to WARN. (#4)
- MySQL integration test + CI job (`mysql` marker) alongside the existing
  Postgres one, covering the MySQL dialect's reflection. (#7)
- Optional index validation (`Config(check_indexes=True)` / `--check-indexes`):
  emits `index_missing` / `index_extra`, compared by column set + uniqueness,
  skipping PK/unique-constraint-backed indexes. Opt-in, defaults to WARN. (#2)
- Optional foreign-key validation (`Config(check_foreign_keys=True)` /
  `--check-foreign-keys`): emits `fk_missing` / `fk_extra`, compared by local
  columns + referred table + referred columns. Opt-in, defaults to WARN. (#3)

- Contribution scaffolding: issue forms (bug / feature), PR template,
  `CONTRIBUTING.md`, `CHANGELOG.md`, `CLAUDE.md`.
- Dependabot for pip and GitHub Actions.
- Release workflow: publishes to PyPI via Trusted Publishing on `v*` tags.
- CodeRabbit AI code review on pull requests (via the CodeRabbit GitHub App,
  configured by `.coderabbit.yaml`).
- CI failure notifications to Slack/Discord (dormant until a webhook is set).
- `pre-commit` hooks: `ormguard-selfcheck` and `ormguard` for downstream users,
  plus a dev config (ruff + selfcheck).

### Changed

- `type_mismatch` now normalizes types per dialect before comparing — folds
  `INT(11)`/`INTEGER`, `CHARACTER VARYING`/`VARCHAR`, `DOUBLE PRECISION`/`DOUBLE`,
  `TINYINT(1)`/`BOOLEAN`, and `TIMESTAMP` spellings — so `check_types` produces
  far fewer false positives (genuine length/precision/tz differences still
  flagged). (#6)
- Version is now derived from git tags via `hatch-vcs` (single source of truth);
  removed the duplicated hardcoded version in `pyproject.toml` and
  `ormguard/__init__.py`.

## [0.1.0] - 2026-06

### Added

- Initial proof of concept: fail-fast schema validation for SQLAlchemy.
- `validate`, `assert_schema`, `validate_many`, `format_matrix` public API.
- FastAPI startup guard (`schema_guard_lifespan`).
- CLI (`python -m ormguard`) with `--selfcheck`.
- Checks: `table_missing`, `column_missing`, `column_extra`,
  `nullable_mismatch`, opt-in `type_mismatch`.

[Unreleased]: https://github.com/gogo1414/ormguard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gogo1414/ormguard/releases/tag/v0.1.0
