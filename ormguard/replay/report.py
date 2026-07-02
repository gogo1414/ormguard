"""Tenant × finding matrix and divergence reporting for multi-tenant replay (v2 M4).

``validate_tenants()`` returns ``{tenant: ValidationReport}``. These helpers turn
that into the audit-style views that make tenant drift obvious:

* :func:`format_tenant_matrix` — one row per distinct finding, one column per
  tenant, so "this column is missing only on larosee" is visible at a glance.
* :func:`find_divergence` — findings present on *some* tenants but not all,
  i.e. the tenants whose migration history branched away from the fleet.
"""

from __future__ import annotations

from ..model import ValidationReport

_PRESENT = "✗"
_ABSENT = "·"


def _finding_key(finding) -> str:
    return f"{finding.kind} @ {finding.location}"


def _finding_map(reports: dict[str, ValidationReport]) -> dict[str, dict[str, object]]:
    """{finding_key: {tenant: Finding}} preserving first-seen ordering."""
    rows: dict[str, dict[str, object]] = {}
    for tenant, report in reports.items():
        for finding in report.findings:
            rows.setdefault(_finding_key(finding), {})[tenant] = finding
    return rows


def find_divergence(reports: dict[str, ValidationReport]) -> dict[str, list[str]]:
    """Findings that hit some tenants but not all: ``{finding_key: [tenants]}``.

    A finding shared by *every* tenant is systematic drift (fix the migration
    once); a finding on a strict subset means tenants have genuinely different
    schemas — the class of bug ormguard v2 exists to catch.
    """
    total = len(reports)
    return {
        key: sorted(by_tenant)
        for key, by_tenant in _finding_map(reports).items()
        if 0 < len(by_tenant) < total
    }


def format_tenant_matrix(reports: dict[str, ValidationReport], *, show_divergence: bool = True) -> str:
    """Render ``{tenant: ValidationReport}`` as a tenant × finding matrix.

    Rows are distinct findings, columns are tenants; ``✗`` marks the tenants a
    finding applies to. Ends with a per-tenant summary line and (optionally) a
    divergence section listing subset-only findings.
    """
    tenants = list(reports)
    if not tenants:
        return "(no tenants)"

    rows = _finding_map(reports)
    if not rows:
        return "\n".join(f"{t:<28} OK" for t in tenants)

    key_width = max(len(k) for k in rows)
    key_width = max(key_width, len("finding"))
    col_widths = [max(len(t), 1) for t in tenants]

    lines = [
        " ".join([f"{'finding':<{key_width}}"] + [f"{t:>{w}}" for t, w in zip(tenants, col_widths)])
    ]
    for key, by_tenant in rows.items():
        cells = [
            f"{(_PRESENT if t in by_tenant else _ABSENT):>{w}}" for t, w in zip(tenants, col_widths)
        ]
        lines.append(" ".join([f"{key:<{key_width}}"] + cells))

    lines.append("")
    for tenant in tenants:
        rep = reports[tenant]
        status = "OK" if rep.ok else f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)"
        lines.append(f"{tenant:<{key_width}} {status}")

    if show_divergence:
        diverged = find_divergence(reports)
        if diverged:
            lines.append("")
            lines.append(f"tenant divergence — {len(diverged)} finding(s) hit only a subset of tenants:")
            for key, subset in diverged.items():
                lines.append(f"  {key} — only on: {', '.join(subset)}")

    return "\n".join(lines)


__all__ = ["format_tenant_matrix", "find_divergence"]
