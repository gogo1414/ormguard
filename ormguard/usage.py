"""Usage-aware ranking of findings.

ormguard knows the ORM disagrees with the DB, but not whether the drifting
column is actually *used*. On a tenant with hundreds of findings that flood
drowns the real bugs. Feed in the SQL your app actually runs — from a SQLAlchemy
``before_cursor_execute`` listener (runtime) or an ``echo`` / query log (offline)
— extract the referenced identifiers, and rank findings **referenced by code =
high, used by nobody = low**.

This module is source-agnostic: you supply the SQL statements; it does the
extraction and ranking.
"""

from __future__ import annotations

import re

from .model import ValidationReport

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def columns_in_sql(statements) -> set[str]:
    """Referenced table/column identifiers across an iterable of SQL strings.

    Uses sqlglot when available (accurate column/table extraction); otherwise
    falls back to a permissive identifier tokenizer (errs toward "referenced",
    so a real bug is never mis-ranked as unused).
    """
    try:
        import sqlglot
        from sqlglot import exp
    except Exception:  # pragma: no cover - sqlglot is an optional extra
        sqlglot = None

    names: set[str] = set()
    for stmt in statements:
        text = str(stmt)
        if sqlglot is None:
            names.update(_IDENT_RE.findall(text))
            continue
        try:
            tree = sqlglot.parse_one(text)
        except Exception:
            names.update(_IDENT_RE.findall(text))
            continue
        if tree is None:
            continue
        for node in tree.find_all(exp.Column):
            names.add(node.name)
        for node in tree.find_all(exp.Table):
            names.add(node.name)
    return names


def _is_referenced(finding, referenced: set[str]) -> bool:
    # A column-level finding ranks on its own column (the table being queried
    # doesn't mean *this* column is used); a table-level finding ranks on the
    # table.
    if finding.column:
        return finding.column in referenced
    return finding.table in referenced


def rank_findings(report: ValidationReport, referenced: set[str]) -> dict[str, list]:
    """Split a report's findings into ``{"high": [...], "low": [...]}`` — high
    are findings whose table/column the supplied SQL references."""
    high, low = [], []
    for finding in report.findings:
        (high if _is_referenced(finding, referenced) else low).append(finding)
    return {"high": high, "low": low}


def format_ranked(ranked: dict[str, list]) -> str:
    """Human-readable ranked view: high-priority (code-referenced) findings first."""
    lines: list[str] = []
    for tier, header in (("high", "referenced by code (high priority)"),
                         ("low", "not referenced (low priority)")):
        items = ranked.get(tier, [])
        lines.append(f"# {header} — {len(items)}")
        for f in items:
            lines.append(f"  {f}")
    return "\n".join(lines)
