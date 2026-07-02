"""validate()/target accepts a list of declarative Bases / MetaData (#41)."""

from __future__ import annotations

from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import declarative_base

from ormguard import assert_schema, validate
from ormguard.model import TABLE_MISSING


def _two_bases():
    Base1 = declarative_base()

    class User(Base1):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)

    Base2 = declarative_base()

    class Product(Base2):
        __tablename__ = "products"
        id = Column(Integer, primary_key=True)

    return Base1, Base2


def test_validate_list_target_merges_and_flags_missing():
    Base1, Base2 = _two_bases()
    engine = create_engine("sqlite://")
    Base1.metadata.create_all(engine)  # only users exists; products missing

    report = validate(engine, [Base1, Base2])
    assert any(f.kind == TABLE_MISSING and f.table == "products" for f in report.findings)
    # users came from Base1, so it must NOT be reported missing
    assert not any(f.kind == TABLE_MISSING and f.table == "users" for f in report.findings)


def test_validate_list_target_clean_when_all_present():
    Base1, Base2 = _two_bases()
    engine = create_engine("sqlite://")
    Base1.metadata.create_all(engine)
    Base2.metadata.create_all(engine)

    report = validate(engine, [Base1, Base2])
    assert report.ok, report.format_text()
    # assert_schema (which routes through validate) also accepts the list
    assert assert_schema(engine, [Base1, Base2], strict=False).ok
