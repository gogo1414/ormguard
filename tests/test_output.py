"""Machine-readable output: JSON, SARIF, GitHub annotations (#44)."""

from __future__ import annotations

import json

from ormguard import github_annotations, to_json, to_sarif
from ormguard.model import (
    COLUMN_MISSING,
    NULLABLE_MISMATCH,
    Finding,
    Severity,
    ValidationReport,
)


def _report(label=None):
    return ValidationReport(
        findings=[
            Finding(Severity.ERROR, COLUMN_MISSING, "users", schema="public",
                    column="email", detail="entity maps this column but the database has none"),
            Finding(Severity.WARN, NULLABLE_MISMATCH, "users", schema="public", column="age"),
        ],
        label=label,
    )


def test_to_json_roundtrips_and_summarizes():
    data = json.loads(to_json(_report()))
    assert data["summary"] == {"findings": 2, "errors": 1, "warnings": 1}
    kinds = {f["kind"] for f in data["findings"]}
    assert kinds == {COLUMN_MISSING, NULLABLE_MISMATCH}
    email = next(f for f in data["findings"] if f["column"] == "email")
    assert email["location"] == "public.users.email"
    assert email["severity"] == "ERROR"


def test_to_sarif_is_valid_and_maps_levels():
    sarif = json.loads(to_sarif(_report()))
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "ormguard"
    rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
    assert rule_ids == {COLUMN_MISSING, NULLABLE_MISMATCH}
    levels = {res["ruleId"]: res["level"] for res in run["results"]}
    assert levels[COLUMN_MISSING] == "error"
    assert levels[NULLABLE_MISMATCH] == "warning"
    loc = run["results"][0]["locations"][0]["logicalLocations"][0]["fullyQualifiedName"]
    assert loc == "public.users.email"


def test_github_annotations_map_severity_and_label():
    lines = github_annotations(_report(label="tenant_a"))
    assert any(line.startswith("::error::") and "public.users.email" in line for line in lines)
    assert any(line.startswith("::warning::") for line in lines)
    assert all("[tenant_a]" in line for line in lines)


def test_output_accepts_report_map():
    reports = {"a": _report(), "b": _report()}
    data = json.loads(to_json(reports))
    assert data["summary"]["findings"] == 4
    assert {f.get("label") for f in data["findings"]} == {"a", "b"}
