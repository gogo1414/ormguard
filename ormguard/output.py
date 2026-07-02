"""Machine-readable output: JSON, SARIF 2.1.0, and GitHub Actions annotations.

Text (`ValidationReport.format_text`) is for humans; these emitters let CI pipe
findings into dashboards, GitHub code scanning (SARIF), or inline workflow
annotations. All accept a single :class:`ValidationReport` or a
``{label: ValidationReport}`` map (from ``validate_fleet`` / ``validate_many`` /
``validate_tenants``).
"""

from __future__ import annotations

import json

from .model import ValidationReport

# Severity name -> SARIF level / GitHub annotation command.
_SARIF_LEVEL = {"ERROR": "error", "WARN": "warning", "INFO": "note", "IGNORE": "none"}
_GH_LEVEL = {"ERROR": "error", "WARN": "warning", "INFO": "notice", "IGNORE": "notice"}


def _iter_reports(reports):
    """Yield ``(label, report)`` for a single report or a ``{label: report}`` map."""
    if isinstance(reports, ValidationReport):
        yield reports.label, reports
    else:
        for label, report in reports.items():
            yield (report.label or label), report


def _finding_dict(finding, label=None) -> dict:
    d = {
        "kind": finding.kind,
        "severity": str(finding.severity),
        "schema": finding.schema,
        "table": finding.table,
        "column": finding.column,
        "location": finding.location,
        "detail": finding.detail,
    }
    if label is not None:
        d["label"] = label
    return d


def to_json(reports, *, indent: int | None = 2) -> str:
    """Serialize findings to JSON: ``{"findings": [...], "summary": {...}}``."""
    findings = []
    errors = warnings = 0
    for label, report in _iter_reports(reports):
        for f in report.findings:
            findings.append(_finding_dict(f, label))
        errors += len(report.errors)
        warnings += len(report.warnings)
    payload = {
        "findings": findings,
        "summary": {"findings": len(findings), "errors": errors, "warnings": warnings},
    }
    return json.dumps(payload, indent=indent)


def to_sarif(reports, *, tool_version: str = "0.1.0") -> str:
    """Serialize findings as SARIF 2.1.0 for GitHub code scanning.

    Each finding kind becomes a rule; each finding a result with a logical
    location (``schema.table.column``) — schema drift has no source file/line.
    """
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for label, report in _iter_reports(reports):
        for f in report.findings:
            rules.setdefault(f.kind, {"id": f.kind, "name": f.kind,
                                      "shortDescription": {"text": f.kind}})
            result = {
                "ruleId": f.kind,
                "level": _SARIF_LEVEL.get(str(f.severity), "warning"),
                "message": {"text": f.detail or f.kind},
                "locations": [{
                    "logicalLocations": [{"fullyQualifiedName": f.location, "kind": "member"}]
                }],
            }
            if label is not None:
                result["properties"] = {"label": label}
            results.append(result)
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "ormguard",
                "informationUri": "https://github.com/gogo1414/ormguard",
                "version": tool_version,
                "rules": list(rules.values()),
            }},
            "results": results,
        }],
    }
    return json.dumps(sarif, indent=2)


def github_annotations(reports) -> list[str]:
    """GitHub Actions workflow commands (``::error::`` / ``::warning::`` …), one
    per finding. Schema drift has no file/line, so annotations attach to the job."""
    lines: list[str] = []
    for label, report in _iter_reports(reports):
        for f in report.findings:
            level = _GH_LEVEL.get(str(f.severity), "warning")
            prefix = f"[{label}] " if label else ""
            msg = f"{prefix}{f.kind} @ {f.location}" + (f" — {f.detail}" if f.detail else "")
            lines.append(f"::{level}::{msg}")
    return lines
