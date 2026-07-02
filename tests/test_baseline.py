"""Baseline / ratchet: accept known findings, fail only on new drift."""

from __future__ import annotations

from ormguard.baseline import (
    apply_baseline,
    fingerprint,
    load,
    report_fingerprints,
    save,
)
from ormguard.model import (
    COLUMN_MISSING,
    NULLABLE_MISMATCH,
    Finding,
    Severity,
    ValidationReport,
)


def _f(kind, table, column=None, schema=None, severity=Severity.ERROR):
    return Finding(severity=severity, kind=kind, table=table, schema=schema, column=column)


def test_fingerprint_is_stable_and_ignores_severity_and_detail():
    a = Finding(Severity.ERROR, COLUMN_MISSING, "users", column="email", detail="x")
    b = Finding(Severity.WARN, COLUMN_MISSING, "users", column="email", detail="different")
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_includes_label():
    f = _f(COLUMN_MISSING, "users", "email")
    assert fingerprint(f) != fingerprint(f, label="tenant_a")
    assert "tenant_a" in fingerprint(f, label="tenant_a")


def test_save_load_roundtrip(tmp_path):
    report = ValidationReport(findings=[_f(COLUMN_MISSING, "users", "email"),
                                        _f(NULLABLE_MISMATCH, "users", "age")])
    path = tmp_path / "baseline.json"
    save(report_fingerprints(report), path)
    accepted = load(path)
    assert accepted == set(report_fingerprints(report))
    assert len(accepted) == 2


def test_apply_baseline_removes_accepted_keeps_new():
    accepted_report = ValidationReport(findings=[_f(COLUMN_MISSING, "users", "email")])
    accepted = set(report_fingerprints(accepted_report))

    # Later run: the known finding plus a brand-new one.
    later = ValidationReport(findings=[
        _f(COLUMN_MISSING, "users", "email"),   # known -> filtered
        _f(NULLABLE_MISMATCH, "users", "age"),  # new   -> kept
    ])
    filtered = apply_baseline(later, accepted)
    kinds = {f.kind for f in filtered.findings}
    assert kinds == {NULLABLE_MISMATCH}
    assert filtered.has_errors() is False or all(f.kind == NULLABLE_MISMATCH for f in filtered.findings)


def test_ratchet_all_known_becomes_clean(tmp_path):
    report = ValidationReport(findings=[_f(COLUMN_MISSING, "users", "email"),
                                        _f(COLUMN_MISSING, "orders", "total")])
    path = tmp_path / "b.json"
    save(report_fingerprints(report), path)

    # Re-running against the same drift, everything is baselined -> no findings left.
    filtered = apply_baseline(report, load(path))
    assert filtered.findings == []
    assert filtered.ok


def test_label_scoped_acceptance(tmp_path):
    # Accept the finding only for tenant_a; tenant_b's identical drift stays new.
    f = _f(COLUMN_MISSING, "users", "email")
    accepted = {fingerprint(f, label="tenant_a")}
    assert apply_baseline(ValidationReport(findings=[f]), accepted, label="tenant_a").findings == []
    assert apply_baseline(ValidationReport(findings=[f]), accepted, label="tenant_b").findings == [f]
