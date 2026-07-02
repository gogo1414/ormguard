"""Dialect-aware normalization of compiled column-type strings.

``type_to_string`` gives us the type as the dialect compiles it, e.g.
``VARCHAR(255)``, ``INT(11)``, ``CHARACTER VARYING(50)``, ``DOUBLE PRECISION``,
``TIMESTAMP WITH TIME ZONE``. Comparing those strings verbatim produces false
``type_mismatch`` findings whenever the ORM and the database spell the *same*
type differently — the reason ``check_types`` ships opt-in.

``normalize_type`` collapses those spellings to a canonical form so equal types
compare equal, while genuinely different types (``VARCHAR(255)`` vs ``TEXT``,
``NUMERIC(10,2)`` vs ``NUMERIC(12,2)``) stay distinct.
"""

from __future__ import annotations

import re

# Base-name synonyms that mean the same thing regardless of dialect. Keys are
# the (whitespace-collapsed, upper-cased) base names; values are canonical.
_SYNONYMS = {
    # integers
    "INT": "INTEGER",
    "INT4": "INTEGER",
    "INTEGER": "INTEGER",
    "INT2": "SMALLINT",
    "SMALLINT": "SMALLINT",
    "INT8": "BIGINT",
    "BIGINT": "BIGINT",
    # booleans
    "BOOL": "BOOLEAN",
    "BOOLEAN": "BOOLEAN",
    # character
    "CHARACTER VARYING": "VARCHAR",
    "VARCHAR": "VARCHAR",
    "VARCHAR2": "VARCHAR",  # Oracle
    "CHARACTER": "CHAR",
    "CHAR": "CHAR",
    "NCHAR": "CHAR",
    "NVARCHAR": "VARCHAR",
    # exact numeric
    "DEC": "NUMERIC",
    "DECIMAL": "NUMERIC",
    "NUMERIC": "NUMERIC",
    # approximate numeric
    "FLOAT4": "REAL",
    "REAL": "REAL",
    "FLOAT8": "DOUBLE",
    "DOUBLE": "DOUBLE",
    "DOUBLE PRECISION": "DOUBLE",
    # date/time
    "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
    "DATETIME": "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
    "TIMESTAMPTZ": "TIMESTAMPTZ",
    "TIME": "TIME",
    "TIME WITHOUT TIME ZONE": "TIME",
    "TIME WITH TIME ZONE": "TIMETZ",
    "TIMETZ": "TIMETZ",
    # binary / large object
    "BYTEA": "BLOB",
    "BLOB": "BLOB",
}

# Types whose parenthesised argument is a cosmetic display width (or otherwise
# not meaningful for drift) and should be dropped before comparison.
_DROP_ARGS = {"INTEGER", "SMALLINT", "BIGINT", "TINYINT", "MEDIUMINT"}

_PAREN_RE = re.compile(r"\(([^)]*)\)")


def _canonical_args(args: str) -> str:
    """Normalize the inside of the parentheses: strip spacing so
    ``NUMERIC(10, 2)`` and ``NUMERIC(10,2)`` match."""
    parts = [p.strip() for p in args.split(",") if p.strip() != ""]
    return ",".join(parts)


def normalize_type(type_str: str, dialect_name: str = "") -> str:
    """Return a canonical form of a compiled type string for comparison.

    Dialect-agnostic synonym folding plus a few dialect-specific rules
    (MySQL integer display widths, ``TINYINT(1)`` as boolean).
    """
    if not type_str:
        return ""

    s = " ".join(type_str.upper().split())

    m = _PAREN_RE.search(s)
    if m:
        args = m.group(1)
        base = (s[: m.start()] + " " + s[m.end():]).strip()
    else:
        args = ""
        base = s
    base = " ".join(base.split())

    # MySQL stores booleans as TINYINT(1); treat that spelling as BOOLEAN.
    if base == "TINYINT" and _canonical_args(args) == "1":
        return "BOOLEAN"

    canonical = _SYNONYMS.get(base, base)

    if canonical in _DROP_ARGS:
        args = ""

    args = _canonical_args(args)
    return f"{canonical}({args})" if args else canonical


def types_equal(expected: str, actual: str, dialect_name: str = "") -> bool:
    """Whether two compiled type strings denote the same type after
    normalization."""
    return normalize_type(expected, dialect_name) == normalize_type(actual, dialect_name)
