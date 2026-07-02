"""Compare expected (ORM) vs actual (DB) schema and emit findings."""

from __future__ import annotations

from ._schema import TableInfo
from .config import Config
from .model import (
    COLUMN_EXTRA,
    COLUMN_MISSING,
    DEFAULT_EXTRA,
    DEFAULT_MISSING,
    FK_EXTRA,
    FK_MISSING,
    INDEX_EXTRA,
    INDEX_MISSING,
    NULLABLE_MISMATCH,
    TABLE_MISSING,
    TYPE_MISMATCH,
    Finding,
    Severity,
)
from .types import normalize_type


def diff_schemas(
    expected: dict[tuple[str | None, str], TableInfo],
    actual: dict[tuple[str | None, str], TableInfo | None],
    config: Config,
    dialect_name: str = "",
) -> list[Finding]:
    findings: list[Finding] = []

    for key, exp in expected.items():
        schema, table = key
        act = actual.get(key)

        if act is None:
            findings.append(
                Finding(
                    severity=config.severity_for(TABLE_MISSING, Severity.ERROR),
                    kind=TABLE_MISSING,
                    schema=schema,
                    table=table,
                    detail="ORM declares this table but it is absent from the database",
                )
            )
            continue

        # Columns the entity expects but the DB lacks -> runtime crash case.
        for cname, ecol in exp.columns.items():
            acol = act.columns.get(cname)
            if acol is None:
                findings.append(
                    Finding(
                        severity=config.severity_for(COLUMN_MISSING, Severity.ERROR),
                        kind=COLUMN_MISSING,
                        schema=schema,
                        table=table,
                        column=cname,
                        detail="entity maps this column but the database has no such column",
                    )
                )
                continue

            # PK columns are always NOT NULL; some dialects (SQLite) misreport
            # them as nullable on reflection, so skip the nullable check there.
            if config.check_nullable and not ecol.primary_key and ecol.nullable != acol.nullable:
                findings.append(
                    Finding(
                        severity=config.severity_for(NULLABLE_MISMATCH, Severity.WARN),
                        kind=NULLABLE_MISMATCH,
                        schema=schema,
                        table=table,
                        column=cname,
                        detail=(
                            f"entity nullable={ecol.nullable} but "
                            f"database nullable={acol.nullable}"
                        ),
                    )
                )

            if config.check_types and normalize_type(
                ecol.type_str, dialect_name
            ) != normalize_type(acol.type_str, dialect_name):
                findings.append(
                    Finding(
                        severity=config.severity_for(TYPE_MISMATCH, Severity.WARN),
                        kind=TYPE_MISMATCH,
                        schema=schema,
                        table=table,
                        column=cname,
                        detail=f"entity type {ecol.type_str} != database type {acol.type_str}",
                    )
                )

            # Server-side default presence (opt-in) — value is not compared, only
            # whether a DB default exists. PK identity defaults are skipped.
            if (
                config.check_server_defaults
                and not ecol.primary_key
                and ecol.has_server_default != acol.has_server_default
            ):
                if ecol.has_server_default:
                    findings.append(
                        Finding(
                            severity=config.severity_for(DEFAULT_MISSING, Severity.WARN),
                            kind=DEFAULT_MISSING,
                            schema=schema,
                            table=table,
                            column=cname,
                            detail="entity sets a server_default but the database column has none",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            severity=config.severity_for(DEFAULT_EXTRA, Severity.WARN),
                            kind=DEFAULT_EXTRA,
                            schema=schema,
                            table=table,
                            column=cname,
                            detail="database column has a default the ORM does not declare",
                        )
                    )

        # Columns in the DB that no entity maps.
        if config.flag_extra_columns:
            for cname in act.columns.keys() - exp.columns.keys():
                findings.append(
                    Finding(
                        severity=config.severity_for(COLUMN_EXTRA, Severity.WARN),
                        kind=COLUMN_EXTRA,
                        schema=schema,
                        table=table,
                        column=cname,
                        detail="database column not mapped by any entity (silently unused)",
                    )
                )

        # Indexes (opt-in), compared by column set + uniqueness.
        if config.check_indexes:
            for k in exp.indexes.keys() - act.indexes.keys():
                idx = exp.indexes[k]
                findings.append(
                    Finding(
                        severity=config.severity_for(INDEX_MISSING, Severity.WARN),
                        kind=INDEX_MISSING,
                        schema=schema,
                        table=table,
                        detail=(
                            f"ORM declares an index on ({', '.join(idx.columns)})"
                            f"{' unique' if idx.unique else ''} but the database has none"
                        ),
                    )
                )
            for k in act.indexes.keys() - exp.indexes.keys():
                idx = act.indexes[k]
                findings.append(
                    Finding(
                        severity=config.severity_for(INDEX_EXTRA, Severity.WARN),
                        kind=INDEX_EXTRA,
                        schema=schema,
                        table=table,
                        detail=(
                            f"database has an index on ({', '.join(idx.columns)})"
                            f"{' unique' if idx.unique else ''} not declared in the ORM"
                        ),
                    )
                )

        # Foreign keys (opt-in), compared by (columns, referred table, referred columns).
        if config.check_foreign_keys:
            for k in exp.foreign_keys.keys() - act.foreign_keys.keys():
                fk = exp.foreign_keys[k]
                findings.append(
                    Finding(
                        severity=config.severity_for(FK_MISSING, Severity.WARN),
                        kind=FK_MISSING,
                        schema=schema,
                        table=table,
                        detail=(
                            f"ORM declares a foreign key ({', '.join(fk.columns)}) -> "
                            f"{fk.referred_table}({', '.join(fk.referred_columns)}) "
                            "but the database has none"
                        ),
                    )
                )
            for k in act.foreign_keys.keys() - exp.foreign_keys.keys():
                fk = act.foreign_keys[k]
                findings.append(
                    Finding(
                        severity=config.severity_for(FK_EXTRA, Severity.WARN),
                        kind=FK_EXTRA,
                        schema=schema,
                        table=table,
                        detail=(
                            f"database has a foreign key ({', '.join(fk.columns)}) -> "
                            f"{fk.referred_table}({', '.join(fk.referred_columns)}) "
                            "not declared in the ORM"
                        ),
                    )
                )

    return findings
