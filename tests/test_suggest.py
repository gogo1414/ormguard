"""Fix suggestions keyed on ownership (#39)."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import Config, format_suggestions, suggest_fixes, validate


def _setup():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        # DB is missing "computed" and has an unmapped column "etl_extra".
        c.execute(text("CREATE TABLE mart (id INTEGER PRIMARY KEY, name VARCHAR, etl_extra VARCHAR)"))

    Base = declarative_base()

    class Mart(Base):
        __tablename__ = "mart"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=True)
        computed = Column(String(64), nullable=False)  # not in DB

    return engine, Base


def test_api_owned_missing_suggests_alembic_add():
    engine, Base = _setup()
    report = validate(engine, Base)
    sug = {s.action: s for s in suggest_fixes(report, Base)}
    assert "alembic_add_column" in sug
    add = sug["alembic_add_column"]
    assert 'op.add_column("mart"' in add.text
    assert '"computed"' in add.text
    assert "nullable=False" in add.text          # rendered from the real Column
    assert "sa.String" in add.text                # rendered from the real type


def test_external_owned_missing_suggests_orm_slimming():
    engine, Base = _setup()
    report = validate(engine, Base, Config(external_tables={"mart"}))
    actions = {s.action for s in suggest_fixes(report, Base, Config(external_tables={"mart"}))}
    assert "orm_remove_column" in actions
    assert "alembic_add_column" not in actions   # don't add to a DB you don't own


def test_extra_column_suggests_map_or_drop():
    engine, Base = _setup()
    report = validate(engine, Base)
    sug = [s for s in suggest_fixes(report, Base) if s.action == "map_or_drop_column"]
    assert sug and "etl_extra" in sug[0].location


def test_format_suggestions_is_readable():
    engine, Base = _setup()
    out = format_suggestions(suggest_fixes(validate(engine, Base), Base))
    assert "alembic_add_column" in out and "op.add_column" in out
