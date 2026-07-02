"""Replay engine: run migrations offline against an in-memory catalog, then
diff the result against ORM metadata.

M1: structural op.* + DAG ordering.
M2: tenant branching — inject ``platform_type`` (x-argument) and
``database_name`` (op.get_bind().engine.url.database) so conditional migrations
execute the right branch per tenant. Raw-SQL DDL parsing (M3) is still stubbed;
``op.execute`` SQL is collected in ``catalog.unparsed``.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..diff import diff_schemas
from ..model import UNPARSED_SQL, Finding, Severity, ValidationReport
from ..orm import build_expected
from .catalog import _DIALECT, Catalog
from .loader import load_ordered
from .recorder import ContextStub, OpRecorder


def replay_migrations(
    migrations_dir: str | Path,
    *,
    platform_type: str | None = None,
    database_name: str | None = None,
) -> Catalog:
    """Replay every migration (root -> head) into a fresh Catalog for one tenant
    profile and return it. With no profile, unconditional branches run."""
    catalog = Catalog()
    recorder = OpRecorder(catalog, database_name=database_name)
    x_args = {"platform_type": platform_type} if platform_type is not None else {}
    context = ContextStub(x_args, bind=recorder.get_bind())

    for module in load_ordered(migrations_dir):
        orig_op = getattr(module, "op", None)
        orig_ctx = getattr(module, "context", None)
        module.op = recorder          # migrations reference the module-global `op`
        module.context = context      # ...and `context` for get_x_argument()
        try:
            module.upgrade()
        finally:
            if orig_op is not None:
                module.op = orig_op
            if orig_ctx is not None:
                module.context = orig_ctx
    return catalog


def _summarize_sql(sql: str, limit: int = 120) -> str:
    flat = " ".join(str(sql).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _diff_against_catalog(metadata, catalog: Catalog, config: Config, label):
    md = getattr(metadata, "metadata", metadata)
    expected = build_expected(md, _DIALECT, config)
    actual = {key: catalog.tables.get(key) for key in expected}
    findings = diff_schemas(expected, actual, config, dialect_name=_DIALECT.name)
    # Raw SQL the replay could not interpret means the computed schema may be
    # incomplete — flag it instead of silently pretending the diff is exact.
    severity = config.severity_for(UNPARSED_SQL, Severity.WARN)
    if severity != Severity.IGNORE:
        findings.extend(
            Finding(
                severity=severity,
                kind=UNPARSED_SQL,
                table="(migration)",
                detail=f"replay could not interpret: {_summarize_sql(sql)}",
            )
            for sql in catalog.unparsed
        )
    return ValidationReport(findings=findings, label=label)


def validate_migrations(
    metadata,
    migrations_dir: str | Path,
    config: Config | None = None,
    *,
    platform_type: str | None = None,
    database_name: str | None = None,
    label: str | None = None,
) -> ValidationReport:
    """Diff ORM ``metadata`` against the schema migrations would produce for one
    tenant profile — no database required."""
    config = config or Config()
    catalog = replay_migrations(
        migrations_dir, platform_type=platform_type, database_name=database_name
    )
    return _diff_against_catalog(metadata, catalog, config, label or database_name)


def validate_tenants(
    metadata,
    migrations_dir: str | Path,
    tenants,
    config: Config | None = None,
) -> dict[str, ValidationReport]:
    """Replay + diff for many tenants at once.

    ``tenants`` is an iterable of ``(platform_type, database_name)`` tuples.
    Returns ``{database_name: ValidationReport}``. Pair with
    ``ormguard.format_matrix`` for a one-line-per-tenant summary.
    """
    config = config or Config()
    reports: dict[str, ValidationReport] = {}
    for platform_type, database_name in tenants:
        # Reports are keyed by database_name; a duplicate would silently drop an
        # earlier tenant's result, so fail loudly instead.
        if database_name in reports:
            raise ValueError(
                f"duplicate database_name {database_name!r} in tenants — "
                "each tenant's database_name must be unique"
            )
        reports[database_name] = validate_migrations(
            metadata, migrations_dir, config,
            platform_type=platform_type, database_name=database_name,
            label=database_name,
        )
    return reports
