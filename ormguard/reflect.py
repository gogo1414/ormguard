"""Reflect the *actual* schema from a live database via SQLAlchemy Inspector.

Only tables that the ORM expects are reflected — we deliberately do not scan
the whole database, so unrelated tables (alembic_version, ETL-owned marts, …)
never show up as noise. Extra-column detection happens *within* mapped tables,
which is exactly the "DB has a column the entity doesn't" case.
"""

from __future__ import annotations

from sqlalchemy import inspect

from ._schema import ColumnInfo, TableInfo, type_to_string
from .config import Config


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
            )
        actual[key] = info
    return actual
