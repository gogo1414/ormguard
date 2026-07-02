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

- Fleet-first multi-tenant validation (`validate_fleet`): each tenant declares
  its own `(engine, bases)` — different target *per tenant*, and multiple
  Bases per target are merged — unlike `validate_many` (N engines, one shared
  target). Reuses the label × finding matrix / `find_divergence` to surface
  "column present on tenant A, absent on tenant B". The matrix helpers moved to
  `ormguard.matrix` (re-exported from `ormguard.replay` for compatibility). (#35)
- Baseline / ratchet (`ormguard/baseline.py` + CLI `--baseline PATH` /
  `--write-baseline`): snapshot accepted findings so CI fails only on **new**
  drift, like a mypy/ESLint baseline. Fingerprints are `kind @ schema.table.column`
  (severity/detail-independent, optionally label-scoped for per-tenant
  acceptance) and the file is human-readable JSON. Lets legacy databases with
  hundreds of known WARNs adopt ormguard without going red. (#37)
- Views & materialized views are no longer false `table_missing`: an ORM-mapped
  name backed by a view or materialized view is reflected (columns compared) and
  marked (`TableInfo.relkind` / `is_view`) instead of reported as a missing
  table. Index/FK/CHECK checks are skipped for views. (#43)
- `Config(server_managed_columns={"created_at", ...})`: columns whose
  nullability / server-default are DB-managed skip `nullable_mismatch` and
  `default_*` noise (presence and type are still checked). Match by bare column
  name or `table.column`. (#43)
- Optional enum validation (`Config(check_enums=True)`): emits `enum_mismatch`
  when an enum column's allowed values differ between the ORM and the database
  (native enums on Postgres/MySQL), naming the differing values. Opt-in, WARN,
  and skipped when either side exposes no enum values. (#5)
- Optional CHECK-constraint validation (`Config(check_constraints=True)`): emits
  `check_missing` / `check_extra`, compared by constraint *name* only (the
  expression text is dialect-rewritten on reflection, so it is not diffed);
  unnamed constraints are skipped. Opt-in, WARN. (#5)
- **v2 (offline replay), M4**: tenant × finding matrix and divergence report
  (`ormguard.replay.format_tenant_matrix` / `find_divergence` — findings that
  hit only a subset of tenants are called out as genuine schema divergence),
  `unparsed_migration_sql` findings surfaced in `ValidationReport` (WARN by
  default) so replay never claims a false "clean", and an `ormguard replay`
  CLI subcommand (`--migrations`, `--metadata`, repeatable `--tenant
  platform:database`, `--tenants-file tenants.json`, `--pythonpath`).
  Statements sqlglot only recognizes as a generic command are now recorded as
  unparsed instead of silently dropped.
- Multi-target config file: `python -m ormguard check --config ormguard.toml`
  validates several targets — e.g. a service DB (offline replay, multi-tenant)
  and a warehouse DB (live reflection), each with its own declarative Base and
  Alembic environment — in one run with a combined exit code. Top-level keys
  act as defaults; per-target overrides; relative paths resolve against the
  config file; `url_env` keeps secrets out of the file. New `config` extra
  installs `tomli` on Python < 3.11.
- **v2 (offline replay), M3**: raw-SQL DDL parsing for `op.execute` via sqlglot
  — CREATE/DROP TABLE and ALTER TABLE ADD/DROP/ALTER/RENAME COLUMN, including
  `DO $$ ... $$` blocks. SQL that can't be interpreted is surfaced in
  `catalog.unparsed` instead of being silently dropped. Adds `sqlglot` to the
  `replay` extra.
- **v2 (offline replay), M2**: tenant-aware replay. Inject a
  `(platform_type, database_name)` profile so conditional migrations execute
  the right branch (`op.get_bind().engine.url.database` /
  `context.get_x_argument()`). New `replay_migrations(platform_type=, database_name=)`
  and `validate_tenants(tenants)` for multi-tenant diff matrices.
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
