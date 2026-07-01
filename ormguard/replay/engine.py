"""Replay engine: run migrations offline against an in-memory catalog, then
diff the result against ORM metadata.

M1 scope: structural ops (create/drop/alter table & column) via the op recorder
and DAG ordering. Tenant branching (M2) and raw-SQL DDL parsing (M3) are stubbed
— ``op.execute`` SQL is collected in ``catalog.unparsed`` rather than applied.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..diff import diff_schemas
from ..model import ValidationReport
from ..orm import build_expected
from .catalog import Catalog, _DIALECT
from .loader import load_ordered
from .recorder import OpRecorder


def replay_migrations(
    migrations_dir: str | Path,
    *,
    database_name: str | None = None,
) -> Catalog:
    """Replay every migration (root -> head) into a fresh Catalog and return it."""
    catalog = Catalog()
    recorder = OpRecorder(catalog, database_name=database_name)

    for module in load_ordered(migrations_dir):
        original = getattr(module, "op", None)
        module.op = recorder  # migrations reference the module-global `op`
        try:
            module.upgrade()
        finally:
            if original is not None:
                module.op = original
    return catalog


def validate_migrations(
    metadata,
    migrations_dir: str | Path,
    config: Config | None = None,
    *,
    database_name: str | None = None,
    label: str | None = None,
) -> ValidationReport:
    """Diff ORM ``metadata`` against the schema migrations would produce — no
    database required."""
    config = config or Config()
    md = getattr(metadata, "metadata", metadata)
    expected = build_expected(md, _DIALECT, config)

    catalog = replay_migrations(migrations_dir, database_name=database_name)
    # Catalog tables are the "actual" side; restrict to expected keys' schemas.
    actual = {key: catalog.tables.get(key) for key in expected}

    findings = diff_schemas(expected, actual, config)
    return ValidationReport(findings=findings, label=label or database_name)
