"""Extract the *expected* schema from SQLAlchemy ORM metadata."""

from __future__ import annotations

from ._schema import ColumnInfo, TableInfo, type_to_string
from .config import Config


def build_expected(metadata, dialect, config: Config) -> dict[tuple[str | None, str], TableInfo]:
    """Turn ``Base.metadata`` into normalized TableInfo keyed by (schema, name)."""
    tables: dict[tuple[str | None, str], TableInfo] = {}
    for table in metadata.tables.values():
        if config.is_table_ignored(table.name):
            continue
        if config.schemas is not None and table.schema not in config.schemas:
            continue

        info = TableInfo(name=table.name, schema=table.schema)
        for col in table.columns:
            if config.is_column_ignored(table.name, col.name):
                continue
            info.columns[col.name] = ColumnInfo(
                name=col.name,
                type_str=type_to_string(col.type, dialect),
                # PK columns are implicitly NOT NULL in SQLAlchemy.
                nullable=bool(col.nullable),
                primary_key=bool(col.primary_key),
            )
        tables[info.key] = info
    return tables
