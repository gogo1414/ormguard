"""Public validation entry points."""

from __future__ import annotations

from sqlalchemy import MetaData

from .config import Config
from .diff import diff_schemas
from .model import SchemaValidationError, ValidationReport
from .orm import build_expected
from .reflect import reflect_actual


def _merge_metadata(sources) -> MetaData:
    """Union an iterable of declarative Bases / MetaData into one MetaData.
    First-seen wins on a duplicate table key; later duplicates are skipped."""
    merged = MetaData()
    for src in sources:
        md = getattr(src, "metadata", src)
        for table in md.tables.values():
            if table.key not in merged.tables:
                table.to_metadata(merged)
    return merged


def _resolve_metadata(target):
    """Accept a declarative Base (has ``.metadata``), a MetaData, or a **list**
    of either — a list is merged into a single MetaData."""
    if isinstance(target, (list, tuple, set)):
        return _merge_metadata(target)
    return getattr(target, "metadata", target)


def validate(engine, target, config: Config | None = None, *, label: str | None = None) -> ValidationReport:
    """Validate ORM ``target`` (declarative Base or MetaData) against the schema
    of the database behind ``engine``. Never raises on drift — inspect the
    returned :class:`ValidationReport` (or call ``.raise_if_errors()``)."""
    config = config or Config()
    metadata = _resolve_metadata(target)
    dialect = engine.dialect

    expected = build_expected(metadata, dialect, config)
    actual = reflect_actual(engine, expected, config)
    findings = diff_schemas(expected, actual, config, dialect_name=dialect.name)

    if label is None:
        label = getattr(getattr(engine, "url", None), "database", None)
    return ValidationReport(findings=findings, label=label)


def assert_schema(engine, target, config: Config | None = None, *, strict: bool = True) -> ValidationReport:
    """Validate and, when ``strict``, raise :class:`SchemaValidationError` if any
    ERROR-level drift is found. Returns the report either way."""
    report = validate(engine, target, config)
    if strict:
        report.raise_if_errors()
    return report


def validate_many(
    engines: dict[str, object],
    target,
    config: Config | None = None,
) -> dict[str, ValidationReport]:
    """Validate the same ORM metadata against several databases (multi-tenant).
    Keys are tenant labels; values are engines."""
    return {
        label: validate(engine, target, config, label=label)
        for label, engine in engines.items()
    }


def format_matrix(reports: dict[str, ValidationReport]) -> str:
    """One-line-per-tenant summary for multi-tenant runs."""
    lines = []
    for label, rep in reports.items():
        status = "OK" if rep.ok else f"{len(rep.errors)}E/{len(rep.warnings)}W"
        lines.append(f"{label:<24} {status}")
    return "\n".join(lines)


__all__ = [
    "validate",
    "assert_schema",
    "validate_many",
    "format_matrix",
    "SchemaValidationError",
]
