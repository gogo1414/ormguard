"""Validation configuration for ormguard."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import (
    CHECK_EXTRA,
    CHECK_MISSING,
    COLUMN_EXTRA,
    DEFAULT_EXTRA,
    DEFAULT_MISSING,
    ENUM_MISMATCH,
    FK_EXTRA,
    FK_MISSING,
    INDEX_EXTRA,
    INDEX_MISSING,
    NULLABLE_MISMATCH,
    TYPE_MISMATCH,
    Severity,
)


@dataclass
class Config:
    """Controls what ormguard checks and how loud each finding is.

    The defaults are tuned for low false positives: presence checks are
    ERROR (these are the cases that crash at runtime), structural nuances
    default to WARN, and type comparison is off until you opt in.
    """

    # Restrict validation to these schemas. None = every schema present in the
    # ORM metadata. Useful for multi-schema setups (e.g. {"aivelabs_sv"}).
    schemas: set[str] | None = None

    # Tables to skip entirely (unqualified name, e.g. "alembic_version").
    ignore_tables: set[str] = field(default_factory=set)

    # Columns to skip, as "table.column" (e.g. "users.legacy_flag").
    ignore_columns: set[str] = field(default_factory=set)

    # Toggles.
    check_nullable: bool = True
    check_types: bool = False  # dialect-dependent; opt in once tuned for your DB.
    check_indexes: bool = False  # dialect-dependent; opt in. Compares by column set + uniqueness.
    check_foreign_keys: bool = False  # opt in. Compares by (columns, referred table, referred columns).
    check_server_defaults: bool = False  # opt in. Compares presence of a DB default, not its value.
    check_constraints: bool = False  # opt in. Compares named CHECK constraints by name (not expression).
    check_enums: bool = False  # opt in. Compares an enum column's allowed values.
    flag_extra_columns: bool = True  # DB columns not present on the entity.

    # Severity per kind — override to make e.g. nullable mismatches fatal.
    severity_overrides: dict[str, Severity] = field(
        default_factory=lambda: {
            COLUMN_EXTRA: Severity.WARN,
            NULLABLE_MISMATCH: Severity.WARN,
            TYPE_MISMATCH: Severity.WARN,
            INDEX_MISSING: Severity.WARN,
            INDEX_EXTRA: Severity.WARN,
            FK_MISSING: Severity.WARN,
            FK_EXTRA: Severity.WARN,
            DEFAULT_MISSING: Severity.WARN,
            DEFAULT_EXTRA: Severity.WARN,
            CHECK_MISSING: Severity.WARN,
            CHECK_EXTRA: Severity.WARN,
            ENUM_MISMATCH: Severity.WARN,
        }
    )

    def severity_for(self, kind: str, default: Severity) -> Severity:
        return self.severity_overrides.get(kind, default)

    def is_table_ignored(self, table: str) -> bool:
        return table in self.ignore_tables

    def is_column_ignored(self, table: str, column: str) -> bool:
        return f"{table}.{column}" in self.ignore_columns
