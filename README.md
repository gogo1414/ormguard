# ormguard

**Fail-fast schema validation for SQLAlchemy.** Bring Hibernate's
`hibernate.ddl-auto=validate` to Python: at startup, reflect the connected
database and verify it matches your ORM entities. Catch entity↔DB drift at
**boot time** instead of as a runtime `column does not exist` error.

## Quickstart (60 seconds)

```bash
pip install ormguard
python -m ormguard --selfcheck   # see it catch drift against in-memory SQLite — no DB, no setup
```

Guard your app at boot so it refuses to start on drift (FastAPI):

```python
from ormguard.integrations.fastapi import schema_guard_lifespan

app = FastAPI(lifespan=schema_guard_lifespan(engine, Base, strict=True))
```

...or fail CI before you ship (exit code 1 on ERROR findings):

```bash
python -m ormguard --url "$DATABASE_URL" --metadata myapp.db:Base
```

...or test your Alembic migrations **without any database at all**:

```bash
python -m ormguard replay --migrations migration/versions --metadata myapp.db:Base
```

That's it. Details and every mode are below.

## The problem

In JPA/Hibernate, `ddl-auto=validate` checks every entity against the live
schema when the app starts and **refuses to boot** on a mismatch. SQLAlchemy
has no equivalent — `create_all()` only creates missing tables, nothing
validates existing ones. So an entity can map a column the database doesn't
have (or ignore a column it does have) and the server starts perfectly fine…
until the request that touches that column blows up in production.

`alembic check` and Atlas help, but both compare against migration metadata /
a live DB through autogenerate and run in CI. ormguard checks the **actual
database the app is about to use, at the moment it boots.**

## Install

```bash
pip install ormguard   # (POC: install from source — see below)
```

## Try it in one line (no DB, no host project)

```bash
python -m ormguard --selfcheck
```

Spins up an in-memory SQLite database with deliberate drift and prints exactly
what ormguard catches — a zero-setup way to see it work or sanity-check an
install.

## Docs

- [docs/DESIGN.md](docs/DESIGN.md) — problem, the Hibernate `validate` analogy, why existing tools don't fit, architecture, roadmap.
- [docs/USAGE.md](docs/USAGE.md) — every usage mode with examples.
- [docs/V2_OFFLINE_REPLAY.md](docs/V2_OFFLINE_REPLAY.md) — the offline multi-tenant Alembic replay mode (the differentiator), shipped M1–M4.

## Use it

### As a startup guard (FastAPI)

```python
from ormguard.integrations.fastapi import schema_guard_lifespan

app = FastAPI(lifespan=schema_guard_lifespan(engine, Base, strict=True))
# strict=True -> app refuses to start on ERROR-level drift
```

### As a function (any framework)

```python
from ormguard import assert_schema, validate

assert_schema(engine, Base, strict=True)      # raise on drift

report = validate(engine, Base)               # or inspect findings yourself
if not report.ok:
    print(report.format_text())
```

### In CI

```bash
python -m ormguard --url "$DATABASE_URL" --metadata myapp.db:Base --schema aivelabs_sv
# exit code 1 on ERROR findings
```

Or drop in the GitHub Action — no install step needed:

```yaml
- uses: gogo1414/ormguard@v1
  with:
    database-url: ${{ secrets.DATABASE_URL }}
    metadata: myapp.db:Base
    args: --schema public --check-indexes   # optional
```

(Until ormguard is on PyPI, set `version:` to a VCS URL, e.g.
`version: git+https://github.com/gogo1414/ormguard@main`.)

Get a team-channel ping when drift is found — one webhook works for Slack or
Discord (add `--notify-on any` to include warnings):

```bash
python -m ormguard --url "$DATABASE_URL" --metadata myapp.db:Base \
  --notify-webhook "$SLACK_OR_DISCORD_WEBHOOK"
```

```yaml
- uses: gogo1414/ormguard@v1
  with:
    database-url: ${{ secrets.DATABASE_URL }}
    metadata: myapp.db:Base
    notify-webhook: ${{ secrets.SLACK_WEBHOOK }}
```

The Action also runs the offline modes — test migrations with **no database in
CI** and surface drift in the GitHub Security tab via SARIF:

```yaml
- uses: gogo1414/ormguard@v1
  id: ormguard
  with:
    command: replay                     # or: check (with config: ormguard.toml)
    migrations: migration/versions
    metadata: myapp.db:Base
    format: sarif
    args: --tenant cafe24:shop_a --tenant larosee:larosee_co_kr
- uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: ${{ steps.ormguard.outputs.sarif-file }}
```

`format: github` instead prints inline `::error::` annotations, and
`--format json|sarif|github` works on the CLI for `validate`, `replay`, and
`check` alike.

### Baselines — adopt on a legacy database without going red

```bash
python -m ormguard --url "$DB" --metadata myapp.db:Base --baseline .ormguard-baseline.json --write-baseline
python -m ormguard --url "$DB" --metadata myapp.db:Base --baseline .ormguard-baseline.json  # only NEW drift fails
```

Works for `replay` too (fingerprints are tenant-scoped in multi-tenant runs),
so CI ratchets: accepted drift stays quiet, new drift fails the build.

### Multi-tenant (one ORM, many databases)

```python
from ormguard import validate_many, format_matrix

reports = validate_many({"larosee": e1, "hmall": e2, "cafe24": e3}, Base)
print(format_matrix(reports))
```

When tenants have genuinely different targets, go fleet-first — each tenant
declares its own engine *and* its own Base(s) (`validate` also accepts a list
of Bases, merged):

```python
from ormguard import validate_fleet, format_tenant_matrix, find_divergence

reports = validate_fleet({
    "larosee": (e1, [ServiceBase, MartBase]),
    "cafe24":  (e2, ServiceBase),
})
print(format_tenant_matrix(reports))   # label × finding matrix + divergence
```

And before slimming a shared ETL model, ask what the fleet actually has in
common — `column_analysis` reflects every tenant and reports, per table, the
**intersection** (safe to map) vs partial columns (and which tenants have them).

### Offline migration replay — no database (v2)

Multi-tenant services often branch inside migrations
(`if platform_type == "cafe24": ...`), so the *same* migration set produces a
*different schema per tenant* — and the tenant that breaks is the one whose DB
doesn't exist yet. ormguard replays your Alembic migrations offline, once per
tenant profile, executing the real branches, and diffs each computed schema
against the ORM:

```bash
pip install "ormguard[replay]"
python -m ormguard replay --migrations migration/versions --metadata myapp.db:Base \
  --tenant cafe24:shop_a --tenant larosee:larosee_co_kr
```

```
finding                          shop_a  larosee_co_kr
column_missing @ users.order          ·              ✗

tenant divergence — 1 finding(s) hit only a subset of tenants:
  column_missing @ users.order — only on: larosee_co_kr
```

Raw SQL in `op.execute()` is parsed too (sqlglot); anything uninterpretable is
flagged as `unparsed_migration_sql` instead of silently ignored. No other tool
executes migration branches per tenant — `alembic check` and Atlas compare one
live DB. See [docs/V2_OFFLINE_REPLAY.md](docs/V2_OFFLINE_REPLAY.md).

### Many databases, one config (`ormguard check`)

Guard a whole deployment — e.g. an API's service DB *and* an ETL pipeline's
warehouse DB, each with its own Base and Alembic environment — from one file:

```toml
# ormguard.toml
[[target]]
name = "service"
mode = "replay"                        # offline, no DB needed
metadata = "src.db:Base"
migrations = "migration/versions"
tenants = [["cafe24", "shop_a"], ["larosee", "larosee_co_kr"]]

[[target]]
name = "warehouse"
mode = "live"                          # reflect a running DB
metadata = "src.models.aace_mart:Base"
url_env = "WAREHOUSE_DB_URL"
schemas = ["aace_mart"]
```

```bash
python -m ormguard check --config ormguard.toml   # exit 1 if any target drifts
```

### From a flood of findings to a to-do list

Real databases produce noisy first runs. ormguard has four levers:

```python
cfg = Config(
    external_tables={"articles", "orders_mart"},         # ETL-owned: lenient (WARN, no extra-column noise)
    server_managed_columns={"created_at", "updated_at"},  # DB-managed: skip nullable/default noise
)
report = validate(engine, Base, cfg)

from ormguard import columns_in_sql, rank_findings, format_ranked, suggest_fixes, format_suggestions

ranked = rank_findings(report, columns_in_sql(sql_log))  # code-referenced findings first
print(format_ranked(ranked))
print(format_suggestions(suggest_fixes(report, Base)))
# column_missing @ users.nickname  ->  op.add_column("users", sa.Column("nickname", sa.String(50)))
```

Ownership tiers make ormguard a *contract* checker (you own the columns you
map, not the whole warehouse table); usage ranking (feed it SQL from a query
log or a SQLAlchemy listener) splits findings into code-referenced high
priority vs unused low priority; and fix suggestions render the actual
`op.add_column(...)` from your ORM's column type.

## What it checks (v1)

| Finding | Default severity | Meaning |
|---|---|---|
| `table_missing` | ERROR | entity declares a table the DB lacks |
| `column_missing` | ERROR | entity maps a column the DB lacks (the crash case) |
| `column_extra` | WARN | DB column not mapped by any entity (silently unused) |
| `nullable_mismatch` | WARN | NOT NULL / NULL disagreement |
| `type_mismatch` | WARN (opt-in) | column type differs — off by default (dialect-dependent) |
| `index_missing` | WARN (opt-in) | ORM declares an index the DB lacks — off by default |
| `index_extra` | WARN (opt-in) | DB has an index not declared in the ORM — off by default |
| `fk_missing` | WARN (opt-in) | ORM declares a foreign key the DB lacks — off by default |
| `fk_extra` | WARN (opt-in) | DB has a foreign key not declared in the ORM — off by default |
| `default_missing` | WARN (opt-in) | ORM sets a server_default the DB column lacks — off by default |
| `default_extra` | WARN (opt-in) | DB column has a default the ORM doesn't declare — off by default |
| `enum_mismatch` | WARN (opt-in) | enum's allowed values differ between ORM and DB (native enums) |
| `check_missing` / `check_extra` | WARN (opt-in) | named CHECK constraint present on one side only |

Configurable via `Config`: restrict schemas, ignore tables/columns, flip
severities, toggle nullable/type/index/foreign-key/default/extra checks.

Index checks (`--check-indexes` / `Config(check_indexes=True)`) compare by column
set and uniqueness — not by name — and skip indexes that merely back a primary
key or unique constraint. Foreign-key checks (`--check-foreign-keys`) compare by
local columns, referred table, and referred columns. Server-default checks
(`--check-defaults`) compare only *whether* a DB default exists — not its value,
which is too dialect-dependent — and skip primary keys. All keep false positives low.

Views and materialized views backing an ORM-mapped name are reflected and
compared (not false `table_missing`), with index/FK/CHECK checks skipped for
them. The **offline multi-tenant Alembic replay** mode (v2) additionally emits
`unparsed_migration_sql` (WARN) when replay cannot interpret raw SQL — the
report never claims a false "clean". Planned next: downgrade replay, more
dialect coverage.

## Develop

```bash
pip install -e ".[dev]"
pytest        # runs against in-memory SQLite, no external DB needed
```

## License

MIT
