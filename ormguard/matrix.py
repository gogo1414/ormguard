"""Label × finding matrix and divergence reporting.

Turns a ``{label: ValidationReport}`` map (from ``validate_fleet``,
``validate_many``, or the v2 ``validate_tenants``) into the audit-style views
that make cross-target drift obvious:

* :func:`format_tenant_matrix` — one row per distinct finding, one column per
  label, so "this column is missing only on larosee" is visible at a glance.
* :func:`find_divergence` — findings present on *some* labels but not all,
  i.e. the targets whose schema diverged from the rest of the fleet.
"""

from __future__ import annotations

from .model import ValidationReport

_PRESENT = "✗"
_ABSENT = "·"


def _finding_key(finding) -> str:
    return f"{finding.kind} @ {finding.location}"


def _finding_map(reports: dict[str, ValidationReport]) -> dict[str, dict[str, object]]:
    """{finding_key: {label: Finding}} preserving first-seen ordering."""
    rows: dict[str, dict[str, object]] = {}
    for label, report in reports.items():
        for finding in report.findings:
            rows.setdefault(_finding_key(finding), {})[label] = finding
    return rows


def find_divergence(reports: dict[str, ValidationReport]) -> dict[str, list[str]]:
    """Findings that hit some labels but not all: ``{finding_key: [labels]}``.

    A finding shared by *every* label is systematic drift (fix it once); a
    finding on a strict subset means those targets have genuinely different
    schemas — e.g. ``armorfit`` has a column ``larosee_test`` lacks.
    """
    total = len(reports)
    return {
        key: sorted(by_label)
        for key, by_label in _finding_map(reports).items()
        if 0 < len(by_label) < total
    }


def format_tenant_matrix(reports: dict[str, ValidationReport], *, show_divergence: bool = True) -> str:
    """Render ``{label: ValidationReport}`` as a label × finding matrix.

    Rows are distinct findings, columns are labels; ``✗`` marks the labels a
    finding applies to. Ends with a per-label summary line and (optionally) a
    divergence section listing subset-only findings.
    """
    labels = list(reports)
    if not labels:
        return "(no targets)"

    rows = _finding_map(reports)
    if not rows:
        return "\n".join(f"{t:<28} OK" for t in labels)

    key_width = max(len(k) for k in rows)
    key_width = max(key_width, len("finding"))
    col_widths = [max(len(t), 1) for t in labels]

    lines = [
        " ".join([f"{'finding':<{key_width}}"] + [f"{t:>{w}}" for t, w in zip(labels, col_widths)])
    ]
    for key, by_label in rows.items():
        cells = [
            f"{(_PRESENT if t in by_label else _ABSENT):>{w}}" for t, w in zip(labels, col_widths)
        ]
        lines.append(" ".join([f"{key:<{key_width}}"] + cells))

    lines.append("")
    for label in labels:
        rep = reports[label]
        status = "OK" if rep.ok else f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)"
        lines.append(f"{label:<{key_width}} {status}")

    if show_divergence:
        diverged = find_divergence(reports)
        if diverged:
            lines.append("")
            lines.append(f"divergence — {len(diverged)} finding(s) hit only a subset of targets:")
            for key, subset in diverged.items():
                lines.append(f"  {key} — only on: {', '.join(subset)}")

    return "\n".join(lines)


__all__ = ["format_tenant_matrix", "find_divergence"]
