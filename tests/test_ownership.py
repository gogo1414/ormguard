"""Table ownership / policy tiers: externally-owned tables (#36)."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import Config, validate
from ormguard.model import COLUMN_EXTRA, COLUMN_MISSING, TABLE_MISSING, Severity


def _drifting_mart():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        # DB is missing "computed" and carries an unmapped ETL column.
        c.execute(text("CREATE TABLE mart (id INTEGER PRIMARY KEY, name VARCHAR, etl_extra VARCHAR)"))

    Base = declarative_base()

    class Mart(Base):
        __tablename__ = "mart"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=True)
        computed = Column(String, nullable=True)  # not in the DB

    return engine, Base


def test_default_ownership_is_strict():
    engine, Base = _drifting_mart()
    report = validate(engine, Base)
    kinds = {(f.kind, f.column) for f in report.findings}
    assert (COLUMN_MISSING, "computed") in kinds
    assert (COLUMN_EXTRA, "etl_extra") in kinds
    assert report.has_errors()  # column_missing is ERROR by default


def test_external_table_downgrades_missing_and_hides_extra():
    engine, Base = _drifting_mart()
    report = validate(engine, Base, Config(external_tables={"mart"}))

    missing = [f for f in report.findings if f.kind == COLUMN_MISSING and f.column == "computed"]
    assert missing and missing[0].severity == Severity.WARN   # downgraded, not ERROR
    assert not any(f.kind == COLUMN_EXTRA for f in report.findings)  # ETL extras not flagged
    assert not report.has_errors()  # externally-owned drift never fails the run


def test_external_table_missing_is_warn_not_error():
    engine = create_engine("sqlite://")  # empty DB — mart table absent entirely
    Base = declarative_base()

    class Mart(Base):
        __tablename__ = "mart"
        id = Column(Integer, primary_key=True)

    report = validate(engine, Base, Config(external_tables={"mart"}))
    tm = [f for f in report.findings if f.kind == TABLE_MISSING]
    assert tm and tm[0].severity == Severity.WARN
    assert not report.has_errors()
