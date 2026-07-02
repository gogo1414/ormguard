"""Fleet-first multi-tenant validation: per-tenant engine + Base(s), then the
cross-tenant divergence matrix."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import find_divergence, format_tenant_matrix, validate_fleet
from ormguard.model import TABLE_MISSING


def _orm():
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String, nullable=True)

    class Order(Base):
        __tablename__ = "orders"
        id = Column(Integer, primary_key=True)

    return Base


def _engine(*ddl):
    e = create_engine("sqlite://")
    with e.begin() as c:
        for stmt in ddl:
            c.execute(text(stmt))
    return e


def test_validate_fleet_surfaces_cross_tenant_divergence():
    Base = _orm()
    ea = _engine(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR)",
        "CREATE TABLE orders (id INTEGER PRIMARY KEY)",
    )
    eb = _engine(
        "CREATE TABLE users (id INTEGER PRIMARY KEY)",  # email missing on tenant b only
        "CREATE TABLE orders (id INTEGER PRIMARY KEY)",
    )

    reports = validate_fleet({"armorfit": (ea, Base), "larosee_test": (eb, Base)})
    assert reports["armorfit"].ok
    assert not reports["larosee_test"].ok

    div = find_divergence(reports)
    email_keys = [k for k in div if "users.email" in k]
    assert email_keys, div
    assert div[email_keys[0]] == ["larosee_test"]  # present only on the diverged tenant

    matrix = format_tenant_matrix(reports)
    assert "armorfit" in matrix and "larosee_test" in matrix


def test_validate_fleet_merges_multiple_bases():
    Base1 = declarative_base()

    class U(Base1):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)

    Base2 = declarative_base()

    class P(Base2):
        __tablename__ = "products"
        id = Column(Integer, primary_key=True)

    # DB has users but not products -> proves Base2 was merged and checked.
    e = _engine("CREATE TABLE users (id INTEGER PRIMARY KEY)")

    reports = validate_fleet({"t": (e, [Base1, Base2])})
    findings = reports["t"].findings
    assert any(f.kind == TABLE_MISSING and f.table == "products" for f in findings)
    assert all(not (f.kind == TABLE_MISSING and f.table == "users") for f in findings)


def test_validate_fleet_all_ok_matrix_is_clean():
    Base = _orm()
    e = _engine(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR)",
        "CREATE TABLE orders (id INTEGER PRIMARY KEY)",
    )
    reports = validate_fleet({"solo": (e, Base)})
    assert reports["solo"].ok
    assert find_divergence(reports) == {}
