"""Fleet-first multi-tenant validation.

The real multi-tenant world is "1 ORM (possibly several Bases) ↔ N tenant DBs
that each have a different target". ``validate_many`` only does N engines against
a *single shared* target; ``validate_fleet`` lets every tenant declare its own
engine **and** its own set of Bases, then reuses the label × finding matrix and
divergence report to surface "column present on armorfit, absent on larosee".
"""

from __future__ import annotations

from ._schema import TableInfo
from .config import Config
from .core import _resolve_metadata, validate
from .matrix import find_divergence, format_tenant_matrix
from .model import ValidationReport
from .orm import build_expected
from .reflect import reflect_actual


def validate_fleet(
    fleet: dict[str, object],
    config: Config | None = None,
) -> dict[str, ValidationReport]:
    """Validate a fleet of tenants, each with its own engine and Base(s).

    ``fleet`` maps a tenant label to ``(engine, bases)`` where ``bases`` is a
    declarative Base / MetaData or a list of them (a list is merged by
    ``validate``). Returns ``{label: ValidationReport}`` — pair with
    :func:`format_tenant_matrix` / :func:`find_divergence` for the cross-tenant
    matrix.
    """
    reports: dict[str, ValidationReport] = {}
    for label, spec in fleet.items():
        engine, bases = spec
        reports[label] = validate(engine, bases, config, label=label)
    return reports


def reflect_fleet(
    fleet: dict[str, object],
    config: Config | None = None,
) -> dict[str, dict[tuple[str | None, str], TableInfo]]:
    """Reflect each tenant's *actual* schema for the ORM-mapped tables.

    Returns ``{label: {(schema, table): TableInfo}}`` with only the tables that
    exist on that tenant. Feeds :func:`column_analysis`.
    """
    config = config or Config()
    out: dict[str, dict[tuple[str | None, str], TableInfo]] = {}
    for label, (engine, bases) in fleet.items():
        expected = build_expected(_resolve_metadata(bases), engine.dialect, config)
        actual = reflect_actual(engine, expected, config)
        out[label] = {k: v for k, v in actual.items() if v is not None}
    return out


def column_analysis(reflected: dict[str, dict[tuple[str | None, str], TableInfo]]) -> dict:
    """Per mapped table, which columns are common to all tenants that have the
    table vs present on only a subset — the basis for slimming an ETL model.

    ``{table_key: {"tenants": [...], "common": [...], "all": [...],
    "by_column": {col: [tenants]}}}``.
    """
    table_keys = {k for tables in reflected.values() for k in tables}
    result: dict = {}
    for tk in sorted(table_keys, key=lambda x: (x[0] or "", x[1])):
        holders = [t for t, tables in reflected.items() if tk in tables]
        by_column: dict[str, list[str]] = {}
        for t in holders:
            for col in reflected[t][tk].columns:
                by_column.setdefault(col, []).append(t)
        result[tk] = {
            "tenants": sorted(holders),
            "common": sorted(c for c, ts in by_column.items() if len(ts) == len(holders)),
            "all": sorted(by_column),
            "by_column": {c: sorted(ts) for c, ts in by_column.items()},
        }
    return result


def format_column_analysis(reflected: dict[str, dict[tuple[str | None, str], TableInfo]]) -> str:
    """Human-readable intersection/union report from :func:`column_analysis`."""
    analysis = column_analysis(reflected)
    if not analysis:
        return "(no tables reflected)"
    lines: list[str] = []
    for tk, info in analysis.items():
        schema, table = tk
        qualified = f"{schema}.{table}" if schema else table
        lines.append(f"== {qualified} (tenants: {', '.join(info['tenants'])}) ==")
        common = info["common"]
        lines.append(f"  common ({len(common)}): {', '.join(common) if common else '—'}")
        partial = [(c, ts) for c, ts in info["by_column"].items() if len(ts) < len(info["tenants"])]
        if partial:
            lines.append("  partial:")
            for col, ts in sorted(partial):
                lines.append(f"    {col} — only on: {', '.join(ts)}")
        lines.append("")
    return "\n".join(lines).rstrip()


__all__ = [
    "validate_fleet",
    "reflect_fleet",
    "column_analysis",
    "format_column_analysis",
    "format_tenant_matrix",
    "find_divergence",
]
