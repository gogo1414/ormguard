# ormguard — Usage Guide

## Install (dev/POC)

```bash
cd ormguard
pip install -e ".[dev]"
```

## 0. See it work with zero setup (self-check)

No host project, no external DB — an in-memory SQLite with deliberate drift:

```bash
python -m ormguard --selfcheck
```

Example output:

```
# selfcheck (in-memory sqlite)
  [ERROR] column_missing @ users.nickname — entity maps this column but the database has no such column
  [ERROR] table_missing @ orders — ORM declares this table but it is absent from the database
  [WARN] nullable_mismatch @ users.age — entity nullable=False but database nullable=True
  [WARN] column_extra @ users.legacy_points — database column not mapped by any entity (silently unused)
  -> 2 error(s), 2 warning(s)
```

## 1. As a function (framework-agnostic)

```python
from ormguard import validate, assert_schema

report = validate(engine, Base)          # never raises — inspect the result
if not report.ok:
    print(report.format_text())

assert_schema(engine, Base, strict=True) # SchemaValidationError on ERROR drift
```

## 2. FastAPI boot guard

```python
from ormguard.integrations.fastapi import schema_guard_lifespan

app = FastAPI(lifespan=schema_guard_lifespan(engine, Base, strict=True))
# strict=True  -> app refuses to boot on ERROR drift (= Hibernate validate)
# strict=False -> warnings are logged, service still starts
```

## 3. CI (exit code)

```bash
python -m ormguard --url "$DATABASE_URL" --metadata myapp.db:Base --schema aivelabs_sv
# exit 1 if there is any ERROR finding
```

Options: `--check-types` (enable type comparison), `--check-indexes`,
`--check-foreign-keys`, `--check-defaults`, `--no-nullable`, `--no-extra`,
`--ignore-table NAME` (repeatable), `--warn-only` (exit 0 even on errors),
`--notify-webhook URL` (Slack/Discord ping on drift).

## 4. Multi-tenant (one ORM, many live databases)

```python
from ormguard import validate_many, format_matrix

reports = validate_many({"larosee": e1, "hmall": e2, "cafe24": e3}, Base)
print(format_matrix(reports))
# larosee   2E/1W
# hmall     OK
# cafe24    OK
```

## 5. Offline migration replay — no database (v2)

Replay your Alembic migrations into an in-memory catalog *per tenant profile*
and diff the computed schema against the ORM. Catches "a brand-new tenant
created from these migrations would not match the entities" **before any
database exists**.

```bash
pip install "ormguard[replay]"

python -m ormguard replay \
  --migrations migration/versions \
  --metadata myapp.db:Base \
  --tenant cafe24:shop_a --tenant larosee:larosee_co_kr
```

Multi-tenant runs print a tenant × finding matrix plus a divergence section
(findings that hit only a subset of tenants — i.e. genuinely diverged schemas):

```
finding                          shop_a  larosee_co_kr
column_missing @ users.order          ·              ✗

shop_a                           OK
larosee_co_kr                    1 error(s), 0 warning(s)

tenant divergence — 1 finding(s) hit only a subset of tenants:
  column_missing @ users.order — only on: larosee_co_kr
```

Tenant profiles can come from a JSON file instead of flags
(`--tenants-file tenants.json`):

```json
[["cafe24", "shop_a"], {"platform_type": "larosee", "database_name": "larosee_co_kr"}]
```

If your models are not importable from the working directory, add
`--pythonpath .` (repeatable).

Python API:

```python
from ormguard.replay import validate_tenants, format_tenant_matrix, find_divergence

reports = validate_tenants(Base, "migration/versions",
                           tenants=[("cafe24", "shop_a"), ("larosee", "larosee_co_kr")])
print(format_tenant_matrix(reports))
diverged = find_divergence(reports)   # {finding_key: [tenants]} — subset-only findings
```

Raw SQL in `op.execute(...)` is parsed (sqlglot) and applied; anything the
parser cannot interpret is reported as an `unparsed_migration_sql` WARN finding
instead of being silently ignored — the report never claims a false "clean".

## 6. Multiple databases in one run (`ormguard check`)

Real deployments rarely guard just one schema. Declare every target — e.g. an
API's service DB and an ETL pipeline's warehouse DB, each with its own Base and
its own Alembic environment — in one `ormguard.toml`:

```toml
pythonpath = ["."]

[[target]]
name = "service"
mode = "replay"                       # offline: no database needed
metadata = "src.db:Base"
migrations = "migration/versions"
schemas = ["aivelabs_sv"]
tenants = [["cafe24", "shop_a"], ["larosee", "larosee_co_kr"]]
# or: tenants_file = "tenants.json"

[[target]]
name = "warehouse-mart"
mode = "live"                         # reflect a running database
metadata = "src.models.aace_mart:Base"
url_env = "WAREHOUSE_DB_URL"          # URL comes from the environment — no secrets in the file
schemas = ["aace_mart"]

[[target]]
name = "warehouse-etl"
mode = "replay"
metadata = "src.models.etl_on_srv:Base"
migrations = "migration/etl_on_srv/versions"
schemas = ["etl_on_srv"]
```

```bash
python -m ormguard check --config ormguard.toml            # run everything
python -m ormguard check --config ormguard.toml --target service   # just one
# exit 1 if any target has ERROR findings (use --warn-only to report only)
```

Top-level keys (`pythonpath`, `schemas`, check toggles, …) act as defaults;
each `[[target]]` can override them. Relative paths resolve against the config
file's directory, so the file lives at the repo root and works from anywhere —
including CI. Per-target keys: `check_types`, `check_indexes`,
`check_foreign_keys`, `check_defaults`, `check_nullable`,
`flag_extra_columns`, `ignore_tables`, `ignore_columns`.

Python < 3.11 needs `pip install "ormguard[config]"` (TOML parser).

## 7. Configuration (Config)

```python
from ormguard import Config, Severity, validate
from ormguard.model import NULLABLE_MISMATCH

cfg = Config(
    schemas={"aivelabs_sv"},                 # only check this schema
    ignore_tables={"alembic_version"},
    ignore_columns={"users.legacy_flag"},
    check_types=True,                        # enable type comparison
    severity_overrides={NULLABLE_MISMATCH: Severity.ERROR},  # make nullable fatal too
)
validate(engine, Base, cfg)
```

## 8. Machine-readable output (JSON / SARIF / GitHub annotations)

Every mode — live, `replay`, and `check` — takes `--format`:

```bash
python -m ormguard --url "$DB" --metadata myapp.db:Base --format sarif > ormguard.sarif
python -m ormguard replay --migrations migration/versions --metadata myapp.db:Base \
  --tenant cafe24:shop_a --format json
python -m ormguard check --config ormguard.toml --format github   # ::error:: annotations
```

`check` collapses all targets into one document with target-qualified labels
(`service:shop_a`). Upload SARIF to GitHub code scanning with
`github/codeql-action/upload-sarif` — the GitHub Action does this wiring for
you (`format: sarif` + the `sarif-file` output).

Python API: `to_json(report_or_map)`, `to_sarif(...)`, `github_annotations(...)`.

## 9. Baseline / ratchet — only new drift fails

```bash
# snapshot today's known drift (exit 0)
python -m ormguard --url "$DB" --metadata myapp.db:Base \
  --baseline .ormguard-baseline.json --write-baseline

# from now on, accepted drift is quiet; NEW drift fails CI
python -m ormguard --url "$DB" --metadata myapp.db:Base --baseline .ormguard-baseline.json
```

Also on `replay` (multi-tenant fingerprints are tenant-scoped, e.g.
`larosee_co_kr :: column_missing @ users.order`, so drift is accepted per
tenant). The file is human-readable JSON — check it in and review changes in PRs.

## 10. Fleet validation (per-tenant targets) & column analysis

`validate_many` is N engines × one target. When tenants have *different*
targets (or several Bases each), use `validate_fleet`:

```python
from ormguard import validate_fleet, format_tenant_matrix, find_divergence

reports = validate_fleet({
    "larosee": (engine1, [ServiceBase, MartBase]),   # list of Bases is merged
    "cafe24":  (engine2, ServiceBase),
})
print(format_tenant_matrix(reports))    # label × finding matrix + divergence
diverged = find_divergence(reports)     # findings on a strict subset of tenants
```

(`validate` / `assert_schema` accept a list of Bases/MetaData too.)

Before slimming a shared model, see what the fleet actually agrees on:

```python
from ormguard import reflect_fleet, format_column_analysis

reflected = reflect_fleet({"a": (e1, Base), "b": (e2, Base)})
print(format_column_analysis(reflected))
# per table: common columns (on every tenant — safe to map) vs partial ("only on: a")
```

## 11. Cutting noise: ownership, server-managed columns, ranking, suggestions

```python
cfg = Config(
    # ETL-owned tables (unqualified names): missing table/column is WARN,
    # DB-only columns never flagged.
    external_tables={"articles", "orders_mart"},
    # DB-managed columns: skip nullable/default comparisons (presence/type still checked).
    server_managed_columns={"created_at", "orders.updated_at"},
)
report = validate(engine, Base, cfg)
```

Prioritize by what your code actually touches, then get concrete fixes:

```python
from ormguard import columns_in_sql, rank_findings, format_ranked
from ormguard import suggest_fixes, format_suggestions

referenced = columns_in_sql(sql_statements)      # from a query log / SQLAlchemy listener
print(format_ranked(rank_findings(report, referenced)))  # high (code-referenced) vs low

print(format_suggestions(suggest_fixes(report, Base)))
# API-owned missing column -> ready-to-paste op.add_column(...) from the ORM type
# externally-owned missing column -> ORM-slimming hint; DB-only column -> map or drop
```

## 12. Enum & CHECK-constraint validation (opt-in)

```python
cfg = Config(check_enums=True, check_constraints=True)
```

`enum_mismatch` names the differing allowed values (native Postgres/MySQL
enums); `check_missing` / `check_extra` compare named CHECK constraints by
name (expressions are dialect-rewritten on reflection, so they aren't diffed).
Both WARN by default.

## Running the test suite

```bash
pytest        # in-memory SQLite, no external DB needed
```
