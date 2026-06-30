"""Compare expected (ORM) vs actual (DB) schema and emit findings."""

from __future__ import annotations

from ._schema import TableInfo
from .config import Config
from .model import (
    COLUMN_EXTRA,
    COLUMN_MISSING,
    NULLABLE_MISMATCH,
    TABLE_MISSING,
    TYPE_MISMATCH,
    Finding,
    Severity,
)


def diff_schemas(
    expected: dict[tuple[str | None, str], TableInfo],
    actual: dict[tuple[str | None, str], TableInfo | None],
    config: Config,
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

            if config.check_types and ecol.type_str != acol.type_str:
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

    return findings
