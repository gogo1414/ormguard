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
- [docs/V2_OFFLINE_REPLAY.md](docs/V2_OFFLINE_REPLAY.md) — spec for the offline multi-tenant Alembic replay mode (the differentiator).

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

### Multi-tenant (one ORM, many databases)

```python
from ormguard import validate_many, format_matrix

reports = validate_many({"larosee": e1, "hmall": e2, "cafe24": e3}, Base)
print(format_matrix(reports))
```

## What it checks (v1)

| Finding | Default severity | Meaning |
|---|---|---|
| `table_missing` | ERROR | entity declares a table the DB lacks |
| `column_missing` | ERROR | entity maps a column the DB lacks (the crash case) |
| `column_extra` | WARN | DB column not mapped by any entity (silently unused) |
| `nullable_mismatch` | WARN | NOT NULL / NULL disagreement |
| `type_mismatch` | WARN (opt-in) | column type differs — off by default (dialect-dependent) |

Configurable via `Config`: restrict schemas, ignore tables/columns, flip
severities, toggle nullable/type/extra checks.

Out of scope for v1 (planned): indexes, foreign keys, defaults, check
constraints, enums, and an **offline multi-tenant Alembic replay** mode that
diffs ORM against the schema migrations *would* produce per tenant — without a
database.

## Develop

```bash
pip install -e ".[dev]"
pytest        # runs against in-memory SQLite, no external DB needed
```

## License

MIT
