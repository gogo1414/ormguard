"""Cross-tenant intersection / union column analysis (#40)."""

from __future__ import annotations

from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import declarative_base

from ormguard import column_analysis, format_column_analysis, reflect_fleet


def _orm():
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)

    return Base


def _engine(create_sql):
    e = create_engine("sqlite://")
    from sqlalchemy import text

    with e.begin() as c:
        c.execute(text(create_sql))
    return e


def test_column_analysis_intersection_and_partial():
    Base = _orm()
    # Same mapped table "users", different actual column sets per tenant.
    a = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR, legacy VARCHAR)")
    b = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR, rfm INTEGER)")
    c = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR)")

    reflected = reflect_fleet({"a": (a, Base), "b": (b, Base), "c": (c, Base)})
    analysis = column_analysis(reflected)
    users = analysis[(None, "users")]

    assert users["tenants"] == ["a", "b", "c"]
    assert users["common"] == ["email", "id"]              # present on all three
    assert users["all"] == ["email", "id", "legacy", "rfm"]
    assert users["by_column"]["legacy"] == ["a"]           # only tenant a
    assert users["by_column"]["rfm"] == ["b"]              # only tenant b


def test_format_column_analysis_lists_common_and_partial():
    Base = _orm()
    a = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR)")
    b = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR, extra VARCHAR)")
    out = format_column_analysis(reflect_fleet({"a": (a, Base), "b": (b, Base)}))
    assert "users" in out
    assert "common" in out
    assert "extra" in out and "only on: b" in out
