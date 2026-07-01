"""Reflect the *actual* schema from a live database via SQLAlchemy Inspector.

Only tables that the ORM expects are reflected — we deliberately do not scan
the whole database, so unrelated tables (alembic_version, ETL-owned marts, …)
never show up as noise. Extra-column detection happens *within* mapped tables,
which is exactly the "DB has a column the entity doesn't" case.
"""

from __future__ import annotations

from sqlalchemy import inspect

from ._schema import ColumnInfo, ForeignKeyInfo, IndexInfo, TableInfo, type_to_string
from .config import Config


def _reflect_foreign_keys(inspector, info: TableInfo, name: str, schema: str | None, config: Config) -> None:
    """Reflect real foreign keys into ``info.foreign_keys``."""
    for fk in inspector.get_foreign_keys(name, schema=schema):
        cols = tuple(fk.get("constrained_columns") or ())
        referred_table = fk.get("referred_table")
        if not cols or not referred_table:
            continue
        if any(config.is_column_ignored(name, c) for c in cols):
            continue
        info_fk = ForeignKeyInfo(
            columns=cols,
            referred_table=referred_table,
            referred_columns=tuple(fk.get("referred_columns") or ()),
            name=fk.get("name") or "",
        )
        info.foreign_keys[info_fk.key] = info_fk


def _reflect_indexes(inspector, info: TableInfo, name: str, schema: str | None, config: Config) -> None:
    """Reflect real indexes, skipping the ones that merely back a primary key
    or a unique constraint (those are auto-created, not declared as ORM
    ``Index()`` objects, so comparing them would be noise)."""
    try:
        pk = inspector.get_pk_constraint(name, schema=schema)
        pk_cols = tuple(pk.get("constrained_columns") or ())
    except Exception:  # pragma: no cover - dialect without PK reflection
        pk_cols = ()
    try:
        unique_colsets = {
            tuple(uc.get("column_names") or ())
            for uc in inspector.get_unique_constraints(name, schema=schema)
        }
    except Exception:  # pragma: no cover - dialect without unique-constraint reflection
        unique_colsets = set()

    for idx in inspector.get_indexes(name, schema=schema):
        raw_cols = idx.get("column_names") or []
        # Expression indexes report a None column — we can't compare those by name.
        if not raw_cols or any(c is None for c in raw_cols):
            continue
        cols = tuple(raw_cols)
        if any(config.is_column_ignored(name, c) for c in cols):
            continue
        if cols == pk_cols or cols in unique_colsets:
            continue
        index = IndexInfo(name=idx.get("name") or "", columns=cols, unique=bool(idx.get("unique")))
        info.indexes[index.key] = index


def reflect_actual(
    engine,
    expected: dict[tuple[str | None, str], TableInfo],
    config: Config,
) -> dict[tuple[str | None, str], TableInfo | None]:
    """For each expected (schema, table), return its DB TableInfo, or None if
    the table is missing from the database."""
    inspector = inspect(engine)
    dialect = engine.dialect
    actual: dict[tuple[str | None, str], TableInfo | None] = {}

    for key, exp in expected.items():
        schema, name = key
        if not inspector.has_table(name, schema=schema):
            actual[key] = None
            continue

        info = TableInfo(name=name, schema=schema)
        for col in inspector.get_columns(name, schema=schema):
            cname = col["name"]
            if config.is_column_ignored(name, cname):
                continue
            info.columns[cname] = ColumnInfo(
                name=cname,
                type_str=type_to_string(col["type"], dialect),
                nullable=bool(col.get("nullable", True)),
                has_server_default=col.get("default") is not None,
            )

        if config.check_indexes:
            _reflect_indexes(inspector, info, name, schema, config)
        if config.check_foreign_keys:
            _reflect_foreign_keys(inspector, info, name, schema, config)

        actual[key] = info
    return actual
