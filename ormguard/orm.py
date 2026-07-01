"""Extract the *expected* schema from SQLAlchemy ORM metadata."""

from __future__ import annotations

from ._schema import ColumnInfo, ForeignKeyInfo, IndexInfo, TableInfo, type_to_string
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
                has_server_default=col.server_default is not None,
            )

        if config.check_indexes:
            for idx in table.indexes:
                cols = tuple(c.name for c in idx.columns)
                if not cols or any(config.is_column_ignored(table.name, c) for c in cols):
                    continue
                index = IndexInfo(name=idx.name or "", columns=cols, unique=bool(idx.unique))
                info.indexes[index.key] = index

        if config.check_foreign_keys:
            for fkc in table.foreign_key_constraints:
                cols = tuple(c.name for c in fkc.columns)
                if not cols or any(config.is_column_ignored(table.name, c) for c in cols):
                    continue
                fk = ForeignKeyInfo(
                    columns=cols,
                    referred_table=fkc.referred_table.name,
                    referred_columns=tuple(el.column.name for el in fkc.elements),
                    name=fkc.name or "",
                )
                info.foreign_keys[fk.key] = fk

        tables[info.key] = info
    return tables
