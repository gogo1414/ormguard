"""Integration test against a real MySQL — exercises the MySQL dialect's
reflection (real NOT NULL, AUTO_INCREMENT PKs, its own type system).

Skipped automatically unless DATABASE_URL_MYSQL is set (and a driver is
installed). Marked `mysql`; CI runs it via `pytest -m mysql` with a MySQL service.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base

from ormguard import Config, validate
from ormguard.model import COLUMN_EXTRA, COLUMN_MISSING, NULLABLE_MISMATCH

pytestmark = pytest.mark.mysql

DATABASE_URL = os.environ.get("DATABASE_URL_MYSQL")

Base = declarative_base()


class Account(Base):
    __tablename__ = "mysql_accounts"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)  # -> missing in DB
    age = Column(Integer, nullable=False)                # -> nullable in DB


@pytest.fixture()
def engine():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL_MYSQL not set")
    try:
        eng = create_engine(DATABASE_URL)
        with eng.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS mysql_accounts"))
            # display_name omitted, age nullable, legacy_col unmapped.
            conn.execute(text(
                "CREATE TABLE mysql_accounts ("
                " id INTEGER AUTO_INCREMENT PRIMARY KEY,"
                " email VARCHAR(255) NOT NULL,"
                " age INTEGER,"
                " legacy_col INTEGER"
                ")"
            ))
    except OperationalError as exc:  # pragma: no cover
        pytest.skip(f"cannot connect to MySQL: {exc}")
    yield eng
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS mysql_accounts"))


def test_mysql_drift_detected(engine):
    report = validate(engine, Base, Config())
    kinds = {(f.kind, f.column) for f in report.findings}

    assert (COLUMN_MISSING, "display_name") in kinds
    assert (NULLABLE_MISMATCH, "age") in kinds       # real NOT NULL reflection
    assert (COLUMN_EXTRA, "legacy_col") in kinds
    assert report.has_errors()
