# ormguard v2 — Offline Multi-Tenant Alembic Replay

> Status: **M1–M4 implemented** (`ormguard/replay/`). Independent of v1
> (runtime validate); enable either or both.

## 1. What and why

v1 validates against a *live* database. But in a multi-tenant deployment the
real danger is **"what schema does a brand-new tenant get when the migrations
build it from scratch?"** — and since that tenant's DB does not exist yet, v1
cannot see it.

v2 replays the migrations **without a database**, once per tenant profile,
computes each tenant's *resulting schema*, and diffs it against the ORM. It
automates what used to be a manual per-tenant drift audit.

`alembic check`/Atlas compare one live DB via autogenerate; they cannot
**actually execute** the `platform_type`/`database_name` conditionals inside
migrations to simulate per-tenant outcomes. That is v2's differentiator.

## 2. Input / output

- **Input**
  - ORM target schema: `Base.metadata` (same extractor as v1).
  - Migration directory: `migration/versions/**` (revision DAG).
  - Tenant profiles: `[(platform_type, database_name), …]`
    (e.g. `("larosee", "larosee_co_kr")`, `("cafe24", "cafe24shop")`) —
    given manually, via `--tenant`, or loaded from a JSON snapshot
    (`--tenants-file`).
- **Output**
  - Per-tenant `ValidationReport` (same model as v1).
  - Tenant × finding matrix + tenant divergence report
    (`format_tenant_matrix`, `find_divergence`).

## 3. Core mechanism — offline replay

Problem: migrations are written to mutate a real DB via side effects
(`op.add_column(...)`, `op.create_table(...)`,
`op.execute("ALTER TABLE … / DO $$ … $$")`), and they branch on
`connection.engine.url.database` and
`context.get_x_argument()["platform_type"]`. To know the resulting schema
without a DB:

1. **In-memory catalog**: `{(schema, table): TableInfo}` that the replay
   mutates (reuses v1's `_schema.TableInfo`).

2. **`op.*` hooks**: intercept the main operations of `alembic.op` and apply
   them to the catalog —
   `create_table`, `drop_table`, `add_column`, `drop_column`, `alter_column`,
   `batch_alter_table`; `op.execute(sql)` delegates to the SQL parser (below);
   `op.bulk_insert`/data changes have no schema effect and are ignored.

3. **Fake offline connection/context**: serve branch inputs from the profile.
   - `op.get_bind().engine.url.database` returns the profile's `database_name`.
   - `context.get_x_argument(as_dictionary=True)` returns
     `{"platform_type": <profile>}`.
   - Guards like `if database_name in [...]: return` and
     `if platform_type != "cafe24": return` **actually execute**.

4. **Raw SQL DDL parser** (`op.execute`): parse with sqlglot (PostgreSQL
   dialect) and apply to the catalog.
   - Supported: `CREATE TABLE`, `ALTER TABLE … ADD/DROP/ALTER/RENAME COLUMN`,
     `DROP TABLE`.
   - `DO $$ … $$` anonymous blocks: DDL inside the body is extracted
     best-effort (regex + sqlglot).
   - Anything unparseable — including statements sqlglot only recognizes as a
     generic command — is recorded in `catalog.unparsed` and surfaced in the
     report as an `unparsed_migration_sql` finding (WARN by default). Never
     silently dropped; the report never claims a false "clean".
   - Pure DML (`INSERT/UPDATE/DELETE`) has no schema effect → skipped.

5. **Revision-ordered replay**: topologically sort the down_revision DAG and
   call each `upgrade()` root→head. Branches/merges (`branch_labels`,
   multiple heads) are handled by the DAG. Each tenant profile replays from a
   fresh catalog.

## 4. Diff & report

- Per-tenant computed catalog vs `Base.metadata` → **v1's `diff_schemas`,
  reused as-is**, plus `unparsed_migration_sql` findings.
- `format_tenant_matrix(reports)` — one row per distinct finding, one column
  per tenant (`✗` = affected), per-tenant summary, and a divergence section.
- `find_divergence(reports)` — findings on a *strict subset* of tenants:
  a finding on **every** tenant is systematic drift (fix the migration once);
  a subset-only finding means tenants genuinely diverged — the class of bug
  this mode exists to catch.

## 5. Public API

```python
from ormguard.replay import (
    replay_migrations,      # one tenant -> Catalog (computed schema)
    validate_migrations,    # one tenant -> ValidationReport
    validate_tenants,       # many tenants -> {tenant: ValidationReport}
    format_tenant_matrix,   # matrix + summary + divergence text
    find_divergence,        # {finding_key: [tenants]} subset-only findings
)

catalog = replay_migrations("migration/versions",
                            platform_type="larosee", database_name="larosee_co_kr")

reports = validate_tenants(Base, "migration/versions",
                           tenants=[("larosee", "larosee_co_kr"), ("cafe24", "cafe24shop")])
print(format_tenant_matrix(reports))
```

CLI:

```bash
python -m ormguard replay --migrations migration/versions --metadata src.db:Base \
    --tenant cafe24:cafe24shop --tenant larosee:larosee_co_kr
# or --tenants-file tenants.json; --pythonpath . if models aren't importable
```

Multiple migration environments (e.g. a service DB and a warehouse DB with
separate Bases) run in one shot via `python -m ormguard check --config
ormguard.toml` — see USAGE.md §6.

## 6. Known limitations

- **Raw SQL coverage**: many branches live in `op.execute` raw SQL, so parser
  coverage bounds accuracy. Everything unhandled is *flagged*, never hidden.
- **Type normalization**: same as v1 — presence/nullable first, types opt-in.
- **Migrations importing app code**: replay stays at the `op`/`sa` level, but a
  migration that imports app modules pulls in those dependencies
  (`--pythonpath` helps make them importable).
- **Profile source**: recommend a checked-in JSON fixture snapshot of the
  tenant registry — no production access needed.

## 7. Milestones

- **M1** ✅ — in-memory catalog + `op.*` hooks
  (create/drop/alter table·column, batch_alter_table) + revision DAG
  topological replay. `replay_migrations()` / `validate_migrations()`.
  Verified by `tests/test_replay_m1.py` (temp migration sets, branches/merges).
- **M2** ✅ — tenant profile `(platform_type, database_name)` injection →
  `op.get_bind().engine.url.database` / `context.get_x_argument()` branching.
  `validate_tenants(tenants)`. `tests/test_replay_m2.py` reproduces the
  real-world pattern (cafe24→order, larosee→rfm, hmall early-return).
- **M3** ✅ — sqlglot-based raw SQL DDL parser (`ormguard/replay/sql.py`):
  CREATE/DROP TABLE, ALTER TABLE ADD/DROP/ALTER/RENAME COLUMN,
  `DO $$ … $$` blocks. Unparseable SQL → `catalog.unparsed`.
  `sqlglot` added to the `replay` extra. `tests/test_replay_m3.py`.
- **M4** ✅ — tenant × finding matrix + divergence report
  (`format_tenant_matrix`, `find_divergence`), `unparsed_migration_sql`
  finding surfaced in reports, `ormguard replay` CLI (tenants via flags or
  JSON file), and multi-target `ormguard check --config ormguard.toml`
  (service + warehouse environments in one run). `tests/test_replay_m4.py`,
  `tests/test_configfile.py`.

## 8. Eval (ground truth)

The manual drift audit of the originating multi-tenant service is the answer
key. v2 succeeds if replay alone — no DB — reproduces:
`campaign_sets.campaign_group_id`/`is_group_added` missing everywhere,
`send_reservation.is_purchase` missing everywhere, larosee
`audience_predefiend_variables.order` missing (a real regression), and the
per-tenant scatter caused by the `enterprise_databases` naming bug.
`tests/test_aace_drift_cases.py` already encodes several of these.
