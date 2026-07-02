"""Turn findings into suggested fixes.

Don't stop at the diff — propose the change, keyed on ownership (#36):

* an **API-owned** table missing a column you map → an Alembic ``op.add_column``
  (you own the DB; add it).
* an **externally-owned** table missing a column you map → an ORM-slimming hint
  (you don't own the DB; drop the column from the model to match reality).
* a DB column no entity maps → map-or-drop it.

Suggestions are best-effort starting points, rendered from the ORM's own Column
objects, not blind guesses.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .core import _resolve_metadata
from .model import COLUMN_EXTRA, COLUMN_MISSING, TABLE_MISSING, ValidationReport


@dataclass(frozen=True)
class Suggestion:
    kind: str       # the finding kind this addresses
    location: str   # schema.table.column
    action: str     # alembic_add_column | orm_remove_column | create_table | map_or_drop_column
    text: str       # the suggested code / instruction


def _column_lookup(metadata) -> dict:
    return {
        (table.schema, table.name, col.name): col
        for table in metadata.tables.values()
        for col in table.columns
    }


def suggest_fixes(report: ValidationReport, target, config: Config | None = None) -> list[Suggestion]:
    """Suggested fixes for a report's findings. ``target`` is the same ORM Base /
    MetaData (or list) you validated, used to render columns from their real
    SQLAlchemy types."""
    config = config or Config()
    columns = _column_lookup(_resolve_metadata(target))
    out: list[Suggestion] = []

    for f in report.findings:
        if f.kind == COLUMN_MISSING:
            if config.is_external(f.table):
                out.append(Suggestion(
                    f.kind, f.location, "orm_remove_column",
                    f"remove `{f.column}` from the ORM model for `{f.table}` — the "
                    f"externally-owned database has no such column",
                ))
            else:
                col = columns.get((f.schema, f.table, f.column))
                type_repr = f"sa.{col.type!r}" if col is not None else "sa.<TYPE>"
                nullable = bool(col.nullable) if col is not None else True
                out.append(Suggestion(
                    f.kind, f.location, "alembic_add_column",
                    f'op.add_column("{f.table}", '
                    f'sa.Column("{f.column}", {type_repr}, nullable={nullable}))',
                ))
        elif f.kind == TABLE_MISSING and not config.is_external(f.table):
            out.append(Suggestion(
                f.kind, f.location, "create_table",
                f'op.create_table("{f.table}", ...)  # create the missing table',
            ))
        elif f.kind == COLUMN_EXTRA:
            out.append(Suggestion(
                f.kind, f.location, "map_or_drop_column",
                f"`{f.location}`: the database has this column but no entity maps it "
                f"— map it on the model or drop it from the database",
            ))

    return out


def format_suggestions(suggestions: list[Suggestion]) -> str:
    """Human-readable list of suggested fixes grouped by action."""
    if not suggestions:
        return "no suggestions"
    lines: list[str] = []
    for s in suggestions:
        lines.append(f"[{s.action}] {s.location}")
        lines.append(f"    {s.text}")
    return "\n".join(lines)
