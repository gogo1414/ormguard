"""Normalized, dialect-light schema representation shared by both sides
of the comparison (ORM-expected and DB-reflected)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type_str: str          # normalized (dialect-compiled, upper-cased) type
    nullable: bool
    primary_key: bool = False


@dataclass(frozen=True)
class IndexInfo:
    name: str
    columns: tuple[str, ...]   # in declared order
    unique: bool = False

    @property
    def key(self) -> tuple[tuple[str, ...], bool]:
        # Indexes are compared by column set + uniqueness, not by name —
        # names differ between the ORM and the database and across dialects.
        return (self.columns, self.unique)


@dataclass(frozen=True)
class ForeignKeyInfo:
    columns: tuple[str, ...]            # local columns, in order
    referred_table: str
    referred_columns: tuple[str, ...]
    name: str = ""

    @property
    def key(self) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        # Compared by (local columns, referred table, referred columns), not by
        # name — constraint names differ between the ORM and dialects.
        return (self.columns, self.referred_table, self.referred_columns)


@dataclass
class TableInfo:
    name: str
    schema: str | None
    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    indexes: dict[tuple[tuple[str, ...], bool], IndexInfo] = field(default_factory=dict)
    foreign_keys: dict[tuple[tuple[str, ...], str, tuple[str, ...]], ForeignKeyInfo] = field(
        default_factory=dict
    )

    @property
    def key(self) -> tuple[str | None, str]:
        return (self.schema, self.name)


def type_to_string(type_engine, dialect) -> str:
    """Best-effort normalized type string. Falls back to repr when a type
    cannot be compiled for the given dialect (common for reflected types)."""
    try:
        return type_engine.compile(dialect=dialect).upper()
    except Exception:
        return str(type_engine).upper()
