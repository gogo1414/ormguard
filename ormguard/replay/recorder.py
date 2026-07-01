"""A stand-in for ``alembic.op`` that records structural operations into a
Catalog instead of executing them against a database.

Injected into each migration module's globals as ``op`` before calling
``upgrade()``. Only schema-affecting operations matter; data operations and
constraints/indexes are accepted and ignored (they don't change column
presence, which is what v1's diff cares about).

Branch inputs (``op.get_bind().engine.url.database`` and
``context.get_x_argument()``) are served from a fixed tenant profile so
conditional migrations execute the right branch. With the default (empty)
profile, replay follows the unconditional path — enough for M1.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy.dialects import postgresql

from .._schema import type_to_string
from .catalog import Catalog

_DIALECT = postgresql.dialect()


class _Url:
    def __init__(self, database: str | None):
        self.database = database


class _Engine:
    def __init__(self, database: str | None):
        self.url = _Url(database)


class _Bind:
    """Minimal object returned by op.get_bind() so branch guards can read
    ``connection.engine.url.database``."""

    def __init__(self, database: str | None):
        self.engine = _Engine(database)
        self.dialect = _DIALECT


class OpRecorder:
    def __init__(self, catalog: Catalog, *, database_name: str | None = None):
        self.catalog = catalog
        self._bind = _Bind(database_name)

    # -- table ops -----------------------------------------------------------
    def create_table(self, name, *columns, schema=None, **kw):
        from sqlalchemy import Column

        cols = [c for c in columns if isinstance(c, Column)]
        self.catalog.create_table(name, cols, schema=schema)

    def drop_table(self, name, schema=None, **kw):
        self.catalog.drop_table(name, schema=schema)

    def rename_table(self, old, new, schema=None, **kw):
        self.catalog.rename_table(old, new, schema=schema)

    # -- column ops ----------------------------------------------------------
    def add_column(self, table, column, schema=None, **kw):
        self.catalog.add_column(table, column, schema=schema)

    def drop_column(self, table, column, schema=None, **kw):
        self.catalog.drop_column(table, column, schema=schema)

    def alter_column(self, table, column, *, new_column_name=None, nullable=None,
                     type_=None, schema=None, **kw):
        type_str = type_to_string(type_, _DIALECT) if type_ is not None else None
        self.catalog.alter_column(
            table, column,
            new_column_name=new_column_name, nullable=nullable,
            type_str=type_str, schema=schema,
        )

    # -- no-ops (don't affect column presence) -------------------------------
    def create_index(self, *a, **k): pass
    def drop_index(self, *a, **k): pass
    def create_foreign_key(self, *a, **k): pass
    def drop_constraint(self, *a, **k): pass
    def create_unique_constraint(self, *a, **k): pass
    def create_primary_key(self, *a, **k): pass
    def create_check_constraint(self, *a, **k): pass
    def bulk_insert(self, *a, **k): pass

    def f(self, name):  # op.f() naming helper
        return name

    # -- deferred to later milestones ----------------------------------------
    def execute(self, sql, *a, **k):
        # M3 will parse DDL out of raw SQL; for now record it as unparsed so it
        # is surfaced rather than silently dropped.
        self.catalog.unparsed.append(str(sql))

    def get_bind(self):
        return self._bind

    # -- batch operations ----------------------------------------------------
    @contextmanager
    def batch_alter_table(self, table, schema=None, **kw):
        yield _BatchOp(self, table, schema)


class _BatchOp:
    """Proxy for ``with op.batch_alter_table('t') as batch_op:`` — forwards to
    the recorder with the table name bound."""

    def __init__(self, op: OpRecorder, table: str, schema: str | None):
        self._op = op
        self._table = table
        self._schema = schema

    def add_column(self, column, **kw):
        self._op.add_column(self._table, column, schema=self._schema)

    def drop_column(self, column, **kw):
        self._op.drop_column(self._table, column, schema=self._schema)

    def alter_column(self, column, **kw):
        self._op.alter_column(self._table, column, schema=self._schema, **kw)

    def create_index(self, *a, **k): pass
    def drop_index(self, *a, **k): pass
    def create_foreign_key(self, *a, **k): pass
    def drop_constraint(self, *a, **k): pass
