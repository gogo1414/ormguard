"""Baseline / ratchet support.

Legacy databases carry hundreds of already-known findings, so they can never go
green. A baseline is a snapshot of *accepted* findings (like a mypy or ESLint
baseline): once written, CI fails only on findings that are **not** in it — i.e.
new drift — while accepted drift is filtered out.

The baseline file is JSON: ``{"version": 1, "accepted": ["<fingerprint>", ...]}``.
Fingerprints are human-readable so the checked-in file reviews cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import ValidationReport


def fingerprint(finding, label: str | None = None) -> str:
    """Stable key for a finding, independent of its severity or detail wording.

    ``label`` (a tenant / database name) is included when given so the same drift
    on different tenants can be accepted individually.
    """
    prefix = f"{label} :: " if label else ""
    return f"{prefix}{finding.kind} @ {finding.location}"


def report_fingerprints(report: ValidationReport, label: str | None = None) -> list[str]:
    """Sorted, de-duplicated fingerprints for every finding in ``report``."""
    return sorted({fingerprint(f, label) for f in report.findings})


def save(fingerprints, path: str | Path) -> None:
    """Write ``fingerprints`` to ``path`` as a baseline file."""
    accepted = sorted(set(fingerprints))
    Path(path).write_text(
        json.dumps({"version": 1, "accepted": accepted}, indent=2) + "\n",
        encoding="utf-8",
    )


def load(path: str | Path) -> set[str]:
    """Read the accepted-fingerprint set from a baseline file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(data.get("accepted", []))


def apply_baseline(
    report: ValidationReport, accepted: set[str], label: str | None = None
) -> ValidationReport:
    """Return a new report with findings already in ``accepted`` removed, so only
    new drift remains (and drives the exit code)."""
    kept = [f for f in report.findings if fingerprint(f, label) not in accepted]
    return ValidationReport(findings=kept, label=report.label)
