"""Opt-in index validation against in-memory SQLite with deliberate drift."""

from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import Config, validate
from ormguard.model import INDEX_EXTRA, INDEX_MISSING

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True)   # unique constraint -> must NOT be flagged
    city = Column(String(50))
    zipcode = Column(String(10))
    __table_args__ = (
        Index("ix_users_city", "city"),                  # will exist in DB -> match
        Index("ix_users_city_zip", "city", "zipcode"),   # dropped in DB -> index_missing
    )


def _make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)                     # table + both ORM indexes + unique
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_users_city_zip"))          # -> index_missing
        conn.execute(text("CREATE INDEX ix_users_zip ON users (zipcode)"))  # -> index_extra
    return engine


def test_indexes_not_checked_by_default():
    report = validate(_make_db(), Base)
    assert not [f for f in report.findings if f.kind in (INDEX_MISSING, INDEX_EXTRA)]


def test_index_missing_and_extra_detected_when_opted_in():
    report = validate(_make_db(), Base, Config(check_indexes=True))

    missing = [f for f in report.findings if f.kind == INDEX_MISSING]
    extra = [f for f in report.findings if f.kind == INDEX_EXTRA]

    # ix_users_city_zip (city, zipcode) is declared in the ORM but absent in DB.
    assert len(missing) == 1
    assert "city" in missing[0].detail and "zipcode" in missing[0].detail

    # ix_users_zip (zipcode) exists in DB but not in the ORM.
    assert len(extra) == 1
    assert "zipcode" in extra[0].detail

    # The unique 'email' index backs a constraint and must not be a false positive.
    assert all("email" not in f.detail for f in extra)
