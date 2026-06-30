"""Integration test against a real PostgreSQL — exercises the dialect paths that
SQLite can't (named schemas, NOT NULL reflection, real types).

Skipped automatically unless DATABASE_URL is set (and a driver is installed).
Marked `postgres`; CI runs it via `pytest -m postgres` with a Postgres service.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base

from ormguard import Config, validate
from ormguard.model import COLUMN_EXTRA, COLUMN_MISSING, NULLABLE_MISMATCH

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ.get("DATABASE_URL")
SCHEMA = "ormguard_it"

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": SCHEMA}
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)  # -> missing in DB
    age = Column(Integer, nullable=False)                # -> nullable in DB


@pytest.fixture()
def engine():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    try:
        eng = create_engine(DATABASE_URL)
        with eng.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
            # display_name omitted, age nullable, legacy_col unmapped.
            conn.execute(text(
                f"CREATE TABLE {SCHEMA}.accounts ("
                " id SERIAL PRIMARY KEY,"
                " email VARCHAR(255) NOT NULL,"
                " age INTEGER,"
                " legacy_col INTEGER"
                ")"
            ))
    except OperationalError as exc:  # pragma: no cover
        pytest.skip(f"cannot connect to Postgres: {exc}")
    yield eng
    with eng.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


def test_postgres_drift_detected(engine):
    report = validate(engine, Base, Config(schemas={SCHEMA}))
    kinds = {(f.kind, f.column) for f in report.findings}

    assert (COLUMN_MISSING, "display_name") in kinds
    assert (NULLABLE_MISMATCH, "age") in kinds       # real NOT NULL reflection
    assert (COLUMN_EXTRA, "legacy_col") in kinds
    assert report.has_errors()
