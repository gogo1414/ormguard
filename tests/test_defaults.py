"""Opt-in server-default presence validation (SQLite, deliberate drift)."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import Config, validate
from ormguard.model import DEFAULT_EXTRA, DEFAULT_MISSING

Base = declarative_base()


class Widget(Base):
    __tablename__ = "widgets"
    id = Column(Integer, primary_key=True)
    status = Column(String(20), server_default=text("'new'"))  # ORM default, DB none -> default_missing
    name = Column(String(50))                                  # ORM none, DB default -> default_extra
    price = Column(Integer, server_default=text("0"))          # both have a default -> match


def _make_db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE widgets ("
            " id INTEGER PRIMARY KEY,"
            " status VARCHAR(20),"            # no default (ORM has one)
            " name VARCHAR(50) DEFAULT 'x',"  # default (ORM has none)
            " price INTEGER DEFAULT 0"        # default (ORM has one too)
            ")"
        ))
    return engine


def test_server_defaults_not_checked_by_default():
    report = validate(_make_db(), Base)
    assert not [f for f in report.findings if f.kind in (DEFAULT_MISSING, DEFAULT_EXTRA)]


def test_default_missing_and_extra_when_opted_in():
    report = validate(_make_db(), Base, Config(check_server_defaults=True))

    missing = [f for f in report.findings if f.kind == DEFAULT_MISSING]
    extra = [f for f in report.findings if f.kind == DEFAULT_EXTRA]

    assert [f.column for f in missing] == ["status"]
    assert [f.column for f in extra] == ["name"]
    # 'price' has a default on both sides, and 'id' is a PK -> neither flagged.
    assert all(f.column not in ("price", "id") for f in missing + extra)
