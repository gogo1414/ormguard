"""Self-contained demo / smoke check.

Runs ormguard against a throwaway in-memory SQLite database seeded with
deliberate drift — no external database and no host project required. Use it to
see what ormguard reports, or as a zero-setup sanity check after install::

    python -m ormguard --selfcheck
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from .core import validate
from .model import ValidationReport

# A small ORM model that intentionally disagrees with the seeded database.
Base = declarative_base()


class _User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    nickname = Column(String(50), nullable=False)  # -> column_missing in DB
    age = Column(Integer, nullable=False)           # -> nullable_mismatch (DB nullable)


class _Order(Base):
    __tablename__ = "orders"                         # -> table_missing
    id = Column(Integer, primary_key=True)


def _seed_drifted_db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        # 'nickname' omitted, 'age' nullable, 'legacy_points' unmapped, no 'orders'.
        conn.execute(text(
            "CREATE TABLE users ("
            " id INTEGER PRIMARY KEY,"
            " email VARCHAR(255) NOT NULL,"
            " age INTEGER,"
            " legacy_points INTEGER"
            ")"
        ))
    return engine


def run_selfcheck() -> ValidationReport:
    """Seed a drifted DB, validate, print the report, and return it."""
    engine = _seed_drifted_db()
    report = validate(engine, Base, label="selfcheck (in-memory sqlite)")
    print(report.format_text())
    print(
        "\nExpected: 2 errors (column_missing nickname, table_missing orders) "
        "+ 2 warnings (nullable age, extra legacy_points)."
    )
    return report


if __name__ == "__main__":  # pragma: no cover
    run_selfcheck()
