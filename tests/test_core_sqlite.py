"""End-to-end validation against a real (in-memory SQLite) database with
intentional drift. No external DB required — proves the engine works.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import Config, Severity, validate
from ormguard.model import COLUMN_EXTRA, COLUMN_MISSING, NULLABLE_MISMATCH, TABLE_MISSING

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    nickname = Column(String(50), nullable=False)   # will be MISSING in DB
    age = Column(Integer, nullable=False)            # DB will have it nullable


class Order(Base):
    __tablename__ = "orders"                         # table absent in DB entirely
    id = Column(Integer, primary_key=True)


def _make_db():
    """Build a DB that deliberately drifts from the ORM above."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        # 'nickname' omitted (column_missing), 'age' nullable (nullable_mismatch),
        # 'legacy_points' present but unmapped (column_extra). 'orders' not created.
        conn.execute(text(
            "CREATE TABLE users ("
            " id INTEGER PRIMARY KEY,"
            " email VARCHAR(255) NOT NULL,"
            " age INTEGER,"
            " legacy_points INTEGER"
            ")"
        ))
    return engine


def _kinds(report):
    return {(f.kind, f.column) for f in report.findings}


def test_detects_all_drift_kinds():
    report = validate(_make_db(), Base)
    kinds = _kinds(report)

    assert (COLUMN_MISSING, "nickname") in kinds
    assert (NULLABLE_MISMATCH, "age") in kinds
    assert (COLUMN_EXTRA, "legacy_points") in kinds
    assert (TABLE_MISSING, None) in kinds  # orders table missing

    # Presence problems are fatal; structural ones are warnings by default.
    assert report.has_errors()
    assert not report.ok


def test_clean_schema_passes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)  # DB exactly matches ORM
    report = validate(engine, Base)
    assert report.ok
    assert report.findings == []


def test_severity_override_makes_nullable_fatal():
    cfg = Config(severity_overrides={NULLABLE_MISMATCH: Severity.ERROR})
    report = validate(_make_db(), Base, cfg)
    nullable_findings = [f for f in report.findings if f.kind == NULLABLE_MISMATCH]
    assert nullable_findings and all(f.severity == Severity.ERROR for f in nullable_findings)


def test_ignore_and_toggles_reduce_noise():
    cfg = Config(flag_extra_columns=False, ignore_columns={"users.nickname"})
    report = validate(_make_db(), Base, cfg)
    kinds = _kinds(report)
    assert not any(k == COLUMN_EXTRA for k, _ in kinds)
    assert (COLUMN_MISSING, "nickname") not in kinds
