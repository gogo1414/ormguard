"""In-memory schema catalog mutated during migration replay.

Same shape as the ORM/DB representation used by v1 (`{(schema, name): TableInfo}`),
so the v1 diff engine can consume a replayed catalog directly as the "actual" side.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from .._schema import ColumnInfo, TableInfo, type_to_string

# Default dialect for compiling column types to normalized strings during replay.
_DIALECT = postgresql.dialect()


def column_from_sa(col) -> ColumnInfo:
    """Build a normalized ColumnInfo from a SQLAlchemy Column object.

    Carries the same metadata the v1 diff compares (server-default presence and
    enum values), so a replayed catalog matches a reflected one when
    ``check_server_defaults`` / ``check_enums`` are enabled."""
    enums = getattr(getattr(col, "type", None), "enums", None)
    return ColumnInfo(
        name=col.name,
        type_str=type_to_string(col.type, _DIALECT),
        nullable=bool(getattr(col, "nullable", True)),
        primary_key=bool(getattr(col, "primary_key", False)),
        has_server_default=getattr(col, "server_default", None) is not None,
        enum_values=tuple(enums) if enums else None,
    )


class Catalog:
    """A mutable set of tables, keyed by (schema, name)."""

    def __init__(self) -> None:
        self.tables: dict[tuple[str | None, str], TableInfo] = {}
        # SQL statements replay could not interpret (filled in M3).
        self.unparsed: list[str] = []

    # -- table ops -----------------------------------------------------------
    def create_table(self, name: str, columns, schema: str | None = None) -> None:
        info = TableInfo(name=name, schema=schema)
        for col in columns:
            info.columns[col.name] = column_from_sa(col)
        self.tables[(schema, name)] = info

    def drop_table(self, name: str, schema: str | None = None) -> None:
        self.tables.pop((schema, name), None)

    def rename_table(self, old: str, new: str, schema: str | None = None) -> None:
        info = self.tables.pop((schema, old), None)
        if info is not None:
            info.name = new
            self.tables[(schema, new)] = info

    # -- column ops ----------------------------------------------------------
    def _table(self, name: str, schema: str | None) -> TableInfo | None:
        return self.tables.get((schema, name))

    def add_column(self, table: str, col, schema: str | None = None) -> None:
        info = self._table(table, schema)
        if info is not None:
            info.columns[col.name] = column_from_sa(col)

    def drop_column(self, table: str, column: str, schema: str | None = None) -> None:
        info = self._table(table, schema)
        if info is not None:
            info.columns.pop(column, None)

    def alter_column(
        self,
        table: str,
        column: str,
        *,
        new_column_name: str | None = None,
        nullable: bool | None = None,
        type_str: str | None = None,
        schema: str | None = None,
    ) -> None:
        info = self._table(table, schema)
        if info is None:
            return
        existing = info.columns.get(column)
        if existing is None:
            return
        new = ColumnInfo(
            name=new_column_name or existing.name,
            type_str=type_str if type_str is not None else existing.type_str,
            nullable=existing.nullable if nullable is None else bool(nullable),
            primary_key=existing.primary_key,
            has_server_default=existing.has_server_default,
            enum_values=existing.enum_values,
        )
        if new_column_name and new_column_name != column:
            info.columns.pop(column, None)
        info.columns[new.name] = new
