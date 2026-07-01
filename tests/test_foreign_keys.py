"""Opt-in foreign-key validation against in-memory SQLite with deliberate drift."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import Config, validate
from ormguard.model import FK_EXTRA, FK_MISSING

Base = declarative_base()


class Org(Base):
    __tablename__ = "orgs"
    id = Column(Integer, primary_key=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("orgs.id"))     # present in DB -> match
    team_id = Column(Integer, ForeignKey("orgs.id"))    # absent in DB -> fk_missing
    manager_id = Column(Integer)                        # ORM: no FK; DB has one -> fk_extra


def _make_db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE orgs (id INTEGER PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE users ("
            " id INTEGER PRIMARY KEY,"
            " org_id INTEGER REFERENCES orgs(id),"       # matches ORM
            " team_id INTEGER,"                          # ORM has FK, DB does not
            " manager_id INTEGER REFERENCES users(id)"   # DB-only FK
            ")"
        ))
    return engine


def test_foreign_keys_not_checked_by_default():
    report = validate(_make_db(), Base)
    assert not [f for f in report.findings if f.kind in (FK_MISSING, FK_EXTRA)]


def test_fk_missing_and_extra_detected_when_opted_in():
    report = validate(_make_db(), Base, Config(check_foreign_keys=True))

    missing = [f for f in report.findings if f.kind == FK_MISSING]
    extra = [f for f in report.findings if f.kind == FK_EXTRA]

    # team_id -> orgs is declared in the ORM but absent from the DB.
    assert len(missing) == 1
    assert "team_id" in missing[0].detail and "orgs" in missing[0].detail

    # manager_id -> users exists in the DB but not in the ORM.
    assert len(extra) == 1
    assert "manager_id" in extra[0].detail and "users" in extra[0].detail

    # org_id -> orgs matches and must not be flagged either way.
    assert all("org_id" not in f.detail for f in missing + extra)
