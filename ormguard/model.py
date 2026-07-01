"""Core data structures for ormguard validation results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    """Finding severity, ordered so comparisons / max() are meaningful."""

    IGNORE = 0
    INFO = 1
    WARN = 2
    ERROR = 3

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


# Stable identifiers for the kinds of drift ormguard detects.
TABLE_MISSING = "table_missing"          # ORM declares a table the DB does not have
COLUMN_MISSING = "column_missing"        # ORM column absent in DB  (the runtime-crash case)
COLUMN_EXTRA = "column_extra"            # DB column not mapped by any ORM entity
NULLABLE_MISMATCH = "nullable_mismatch"  # NOT NULL / NULL disagreement
TYPE_MISMATCH = "type_mismatch"          # column type disagreement (opt-in)
INDEX_MISSING = "index_missing"          # ORM declares an index the DB lacks (opt-in)
INDEX_EXTRA = "index_extra"              # DB has an index no ORM entity declares (opt-in)


@dataclass(frozen=True)
class Finding:
    """A single point of disagreement between ORM and database."""

    severity: Severity
    kind: str
    table: str
    schema: str | None = None
    column: str | None = None
    detail: str = ""

    @property
    def location(self) -> str:
        qualified = f"{self.schema}.{self.table}" if self.schema else self.table
        return f"{qualified}.{self.column}" if self.column else qualified

    def __str__(self) -> str:
        return f"[{self.severity}] {self.kind} @ {self.location}" + (
            f" — {self.detail}" if self.detail else ""
        )


class SchemaValidationError(RuntimeError):
    """Raised when strict validation finds ERROR-level drift."""

    def __init__(self, report: "ValidationReport"):
        self.report = report
        super().__init__(
            f"ormguard: schema validation failed with "
            f"{len(report.errors)} error(s):\n{report.format_text()}"
        )


@dataclass
class ValidationReport:
    """Result of validating one engine against one set of ORM metadata."""

    findings: list[Finding] = field(default_factory=list)
    label: str | None = None  # e.g. tenant / database name, for multi-tenant runs

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARN]

    def has_errors(self) -> bool:
        return any(f.severity == Severity.ERROR for f in self.findings)

    @property
    def ok(self) -> bool:
        return not self.has_errors()

    def raise_if_errors(self) -> "ValidationReport":
        if self.has_errors():
            raise SchemaValidationError(self)
        return self

    def format_text(self) -> str:
        if not self.findings:
            head = "ormguard: OK — ORM matches database"
            return f"{head} ({self.label})" if self.label else head
        lines: list[str] = []
        if self.label:
            lines.append(f"# {self.label}")
        # ERROR first, then WARN, then the rest.
        for f in sorted(self.findings, key=lambda x: -int(x.severity)):
            lines.append(f"  {f}")
        lines.append(
            f"  -> {len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )
        return "\n".join(lines)
