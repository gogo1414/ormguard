"""Views / materialized views awareness and server-managed column exceptions."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import Config, validate
from ormguard.model import DEFAULT_MISSING, NULLABLE_MISMATCH, TABLE_MISSING
from ormguard.reflect import _relkind


# ---- relkind detection ---------------------------------------------------

class _StubInspector:
    def __init__(self, tables=(), views=(), mviews=()):
        self._t, self._v, self._m = set(tables), set(views), set(mviews)

    def has_table(self, name, schema=None):
        return name in self._t

    def get_view_names(self, schema=None):
        return list(self._v)

    def get_materialized_view_names(self, schema=None):
        return list(self._m)


def test_relkind_detects_table_view_mv_and_missing():
    insp = _StubInspector(tables={"t"}, views={"v"}, mviews={"mv"})
    assert _relkind(insp, "t", None) == "table"
    assert _relkind(insp, "v", None) == "view"
    assert _relkind(insp, "mv", None) == "materialized_view"
    assert _relkind(insp, "nope", None) is None


def test_relkind_handles_dialect_without_mv_support():
    class Insp:  # no get_materialized_view_names attribute
        def has_table(self, n, schema=None):
            return False

        def get_view_names(self, schema=None):
            return []

    assert _relkind(Insp(), "x", None) is None


# ---- view-backed mapping is not table_missing ----------------------------

def test_view_backed_mapping_not_reported_missing():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE base_t (id INTEGER PRIMARY KEY, name VARCHAR)"))
        c.execute(text("CREATE VIEW v AS SELECT id, name FROM base_t"))

    Base = declarative_base()

    class V(Base):
        __tablename__ = "v"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=True)

    report = validate(engine, Base)
    assert not any(f.kind == TABLE_MISSING for f in report.findings), report.format_text()
    assert report.ok


# ---- server-managed column exceptions ------------------------------------

def _server_managed_setup():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        # DB column is nullable and has no default...
        c.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, created_at DATETIME)"))

    Base = declarative_base()

    class T(Base):
        __tablename__ = "t"
        id = Column(Integer, primary_key=True)
        # ...but the ORM declares it NOT NULL with a server default.
        created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    return engine, Base


def test_server_managed_column_flags_without_config():
    engine, Base = _server_managed_setup()
    kinds = {f.kind for f in validate(engine, Base, Config(check_server_defaults=True)).findings}
    assert NULLABLE_MISMATCH in kinds
    assert DEFAULT_MISSING in kinds


def test_server_managed_column_suppresses_nullable_and_default():
    engine, Base = _server_managed_setup()
    cfg = Config(check_server_defaults=True, server_managed_columns={"created_at"})
    kinds = {f.kind for f in validate(engine, Base, cfg).findings}
    assert NULLABLE_MISMATCH not in kinds
    assert DEFAULT_MISSING not in kinds
