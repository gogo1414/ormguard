"""Usage-aware ranking of findings (#38)."""

from __future__ import annotations

from ormguard import columns_in_sql, format_ranked, rank_findings
from ormguard.model import COLUMN_MISSING, TABLE_MISSING, Finding, Severity, ValidationReport


def test_columns_in_sql_extracts_tables_and_columns():
    refs = columns_in_sql([
        "SELECT id, email FROM users WHERE age > 21",
        "UPDATE orders SET total = 5 WHERE id = 1",
    ])
    assert {"email", "age", "users", "orders", "total"} <= refs


def test_rank_findings_splits_high_and_low():
    report = ValidationReport(findings=[
        Finding(Severity.ERROR, COLUMN_MISSING, "users", column="email"),   # referenced
        Finding(Severity.WARN, COLUMN_MISSING, "users", column="legacy_x"),  # not referenced
    ])
    referenced = columns_in_sql(["SELECT email FROM users"])
    ranked = rank_findings(report, referenced)
    assert [f.column for f in ranked["high"]] == ["email"]
    assert [f.column for f in ranked["low"]] == ["legacy_x"]


def test_table_level_finding_ranks_on_table():
    # A table-level finding (no column) is high when the table is queried...
    report = ValidationReport(findings=[Finding(Severity.WARN, TABLE_MISSING, "orders")])
    assert rank_findings(report, columns_in_sql(["SELECT 1 FROM orders"]))["high"]


def test_unused_column_stays_low_even_if_table_queried():
    # ...but an unreferenced column stays low even if its table is queried.
    report = ValidationReport(findings=[Finding(Severity.WARN, COLUMN_MISSING, "orders", column="zzz")])
    ranked = rank_findings(report, columns_in_sql(["SELECT id FROM orders"]))
    assert ranked["low"] and not ranked["high"]


def test_format_ranked_orders_high_first():
    report = ValidationReport(findings=[
        Finding(Severity.WARN, COLUMN_MISSING, "t", column="used"),
        Finding(Severity.WARN, COLUMN_MISSING, "t", column="unused"),
    ])
    out = format_ranked(rank_findings(report, {"used"}))
    assert out.index("high priority") < out.index("low priority")
    assert "used" in out and "unused" in out
