# ormguard — Design

## 1. The problem

With SQLAlchemy, **the server starts fine even when the ORM entities and the
actual DB schema disagree.** Nothing cross-checks the two at boot.

- Entity has a column the DB lacks → the first request that touches it blows
  up at runtime with `column does not exist`.
- DB has a column no entity maps → it is silently unused (migrated but never
  mapped, etc.).

Because the failure only manifests when a specific feature runs, it is often
discovered in production long after the deploy — not right after it.

## 2. The JPA/Hibernate contrast (the founding idea)

JPA/Hibernate has `hibernate.ddl-auto=validate`. At boot it checks every
entity against the live schema and, on any mismatch, throws
`SchemaManagementException` — **the app refuses to start.** The class of bug
"entity≠DB but the service hums along until it explodes" is structurally
impossible.

SQLAlchemy has no equivalent. `create_all()` only creates missing tables; it
neither validates nor alters existing schema.

> **ormguard = Hibernate's `ddl-auto=validate`, for SQLAlchemy.**

## 3. Two different consistency checks, kept distinct

Same goal (entity↔DB consistency), different **moment of checking**. ormguard
ships both: **A** is the v1 core, **B** is the v2 replay mode.

| | **A. Runtime validate (v1)** | **B. Offline migration replay (v2)** |
|---|---|---|
| Compares | Entity ↔ **the actually connected DB** | Entity ↔ **the schema migrations would produce** |
| Needs a DB? | Yes (the one the app uses) | No (fully static) |
| When | App boot / CI against a DB | In CI, before any DB exists |
| Catches | **All** drift (manual DB edits, ETL changes, missed migrations) | Migration branch bugs, "a fresh tenant would be broken" |

- **A** sees the real DB, so it catches drift from any cause — but only for a
  DB it can connect to.
- **B** needs no DB and can predict future tenants — but only sees drift that
  entered through the migration path.

## 4. Why existing tools don't fit

- **`alembic check`**: points autogenerate at one live DB. It's a CI/dev tool
  with known blind spots (server_default off by default, type comparison
  skipped when one side is a default, …), and above all it does not guarantee
  *the DB this app is about to use* is right *at the moment it boots*. It also
  cannot execute the tenant branches inside migrations.
- **Atlas**: live-DB drift detection is paid; a Go binary sits heavily on a
  Python stack.
- **migra / sqlalchemy-diff**: DB↔DB diffing, not entity↔live-DB.

ormguard validates *the exact database the app is about to use, at boot* (v1),
and *the schema each tenant's migration history would produce, with no
database at all* (v2).

## 5. v1 checks

| Finding | Default severity | Meaning |
|---|---|---|
| `table_missing` | ERROR | entity declares a table the DB lacks |
| `column_missing` | ERROR | entity maps a column the DB lacks (the runtime-crash case) |
| `column_extra` | WARN | DB column not mapped by any entity |
| `nullable_mismatch` | WARN | NOT NULL / NULL disagreement |
| `type_mismatch` | WARN (opt-in) | column type differs — off by default (dialect-dependent) |
| `index_missing` / `index_extra` | WARN (opt-in) | index disagreement — compared by column set + uniqueness |
| `fk_missing` / `fk_extra` | WARN (opt-in) | foreign-key disagreement |
| `default_missing` / `default_extra` | WARN (opt-in) | server-default *presence* disagreement |
| `unparsed_migration_sql` | WARN (v2 replay only) | replay could not interpret raw SQL — manual review needed |

Design principle: **keep false positives low.** Presence (what actually
crashes at runtime) is ERROR; structural nuance is WARN; type comparison only
when enabled. PK columns are excluded from the nullable check because some
dialects (SQLite) reflect them incorrectly.

ormguard reflects **only the tables the ORM knows about** — it never scans the
whole DB. `alembic_version` or ETL-owned tables don't show up as noise.
"Column in DB but not on the entity" is checked only *inside mapped tables*.

## 6. Architecture

```
validate(engine, Base, config)                     # v1: live DB
  ├─ orm.build_expected(metadata)      # ORM target schema → {(schema,table): TableInfo}
  ├─ reflect.reflect_actual(engine)    # live schema (Inspector) → same shape
  └─ diff.diff_schemas(expected, actual) → [Finding] → ValidationReport

validate_tenants(Base, migrations_dir, tenants)    # v2: no DB
  ├─ replay.load_ordered(dir)          # revision DAG → topological order
  ├─ replay.OpRecorder / ContextStub   # op.* hooks + tenant profile injection
  ├─ replay.sql.apply_sql(...)         # raw SQL DDL via sqlglot (op.execute)
  └─ diff.diff_schemas(...)            # same diff engine as v1, per tenant
```

- `_schema.py` — normalized representation shared by both sides (ColumnInfo / TableInfo).
- `model.py` — Severity, Finding, ValidationReport, SchemaValidationError.
- `config.py` — schema restriction, ignores, severity overrides, toggles.
- `configfile.py` — multi-target `ormguard.toml` (service DB + warehouse DB in one run).
- `integrations/fastapi.py` — `schema_guard_lifespan(...)` boot guard.
- `cli.py` — `python -m ormguard` (+ `replay`, `check` subcommands) with CI exit codes.
- `core.py` — `validate`, `assert_schema`, `validate_many`, `format_matrix`.
- `replay/` — offline replay engine (catalog, loader, recorder, sql, report).

Pure SQLAlchemy dependency. FastAPI is optional; `alembic`/`sqlglot` only for
the `replay` extra; `tomli` only for `check` on Python < 3.11.

## 7. Validation strategy

- **Self-tests**: `tests/` — deliberate drift against in-memory SQLite covers
  every finding kind; replay milestones (M1–M4) have dedicated suites that
  reproduce real-world branching patterns. No external DB needed.
- **Self-demo**: `python -m ormguard --selfcheck` — one line, shows it working.
- **Real-world ground truth**: a manual audit of a production multi-tenant
  service (see §9) serves as the answer key the replay mode must reproduce;
  `tests/test_aace_drift_cases.py` encodes those cases.

## 8. Roadmap

- **v1** ✅: runtime entity↔DB validate, FastAPI guard, CLI, multi-tenant
  matrix, opt-in index/FK/default checks, webhook notify, GitHub Action.
- **v2** ✅ (M1–M4): offline multi-tenant Alembic replay — replay migrations
  per tenant profile `(platform_type, database_name)` with `op.*` hooks +
  raw-SQL DDL parsing, executing real branches; diff each tenant's computed
  schema against the ORM; tenant × finding matrix + divergence report;
  `ormguard replay` CLI; `ormguard check` multi-target config
  (service DB + warehouse DB in one run). **Predicts "a fresh tenant would be
  broken" with no database — no existing tool does this.**
- **Next**: check constraints, enums, more dialect coverage, downgrade replay,
  Alembic-branch linting.

## 9. The real-world case that motivated this (multi-tenant)

The originating service is a PostgreSQL multi-tenant API where 40 of 66
migrations branch on `connection.engine.url.database` (= mall_id) and
`platform_type`. The same migration set yields a *different schema per tenant*
(larosee/hmall/cafe24/imweb). A manual audit found columns missing on every
tenant (`campaign_sets.campaign_group_id` — a runtime error on all platforms)
and a naming bug (`enterprise_databases`) that would give brand-new tenants an
empty ETL table. Automating that audit — before boot, before the tenant even
exists — is exactly what v2 does.

The same organization also runs a separate warehouse database (ETL-owned
schemas) with its own declarative Bases and its own Alembic environments —
the reason `ormguard check` validates *multiple targets* from one config file.
