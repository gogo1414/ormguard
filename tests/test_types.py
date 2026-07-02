"""Unit tests for dialect-aware type normalization and its effect on
``type_mismatch`` findings."""

from __future__ import annotations

import pytest

from ormguard._schema import ColumnInfo, TableInfo
from ormguard.config import Config
from ormguard.diff import diff_schemas
from ormguard.model import TYPE_MISMATCH
from ormguard.types import normalize_type, types_equal


@pytest.mark.parametrize(
    "a, b",
    [
        # integer spellings
        ("INTEGER", "INT"),
        ("INTEGER", "INT4"),
        ("INT(11)", "INTEGER"),          # MySQL display width
        ("BIGINT(20)", "INT8"),
        ("SMALLINT", "INT2"),
        # booleans (incl. MySQL TINYINT(1))
        ("BOOLEAN", "BOOL"),
        ("TINYINT(1)", "BOOLEAN"),
        # character
        ("VARCHAR(255)", "CHARACTER VARYING(255)"),
        ("CHAR(3)", "CHARACTER(3)"),
        # numeric spacing / synonyms
        ("NUMERIC(10, 2)", "NUMERIC(10,2)"),
        ("DECIMAL(10,2)", "NUMERIC(10,2)"),
        # approximate numeric
        ("DOUBLE PRECISION", "DOUBLE"),
        ("REAL", "FLOAT4"),
        # date/time
        ("TIMESTAMP", "TIMESTAMP WITHOUT TIME ZONE"),
        ("TIMESTAMP", "DATETIME"),
        ("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ"),
        # binary
        ("BYTEA", "BLOB"),
        # case / whitespace only
        ("varchar(255)", "VARCHAR(255)"),
    ],
)
def test_equivalent_types_normalize_equal(a, b):
    assert types_equal(a, b), f"{a!r} should equal {b!r} -> {normalize_type(a)} vs {normalize_type(b)}"


@pytest.mark.parametrize(
    "a, b",
    [
        ("VARCHAR(255)", "TEXT"),
        ("VARCHAR(255)", "VARCHAR(100)"),   # length matters
        ("NUMERIC(10,2)", "NUMERIC(12,2)"),  # precision matters
        ("INTEGER", "BIGINT"),
        ("BOOLEAN", "SMALLINT"),
        ("TINYINT(4)", "BOOLEAN"),          # only TINYINT(1) is boolean
        ("TIMESTAMP", "TIMESTAMPTZ"),        # tz-awareness matters
    ],
)
def test_distinct_types_stay_distinct(a, b):
    assert not types_equal(a, b)


def _cols(type_str):
    return {"c": ColumnInfo(name="c", type_str=type_str, nullable=True)}


def _diff(expected_type, actual_type):
    key = (None, "t")
    expected = {key: TableInfo(name="t", schema=None, columns=_cols(expected_type))}
    actual = {key: TableInfo(name="t", schema=None, columns=_cols(actual_type))}
    cfg = Config(check_types=True, flag_extra_columns=False)
    return diff_schemas(expected, actual, cfg, dialect_name="mysql")


def test_no_type_mismatch_for_equivalent_spelling():
    findings = _diff("INTEGER", "INT(11)")
    assert not any(f.kind == TYPE_MISMATCH for f in findings)


def test_type_mismatch_for_real_difference():
    findings = _diff("VARCHAR(255)", "TEXT")
    type_findings = [f for f in findings if f.kind == TYPE_MISMATCH]
    assert len(type_findings) == 1
    # the original (un-normalized) spellings are preserved in the message
    assert "VARCHAR(255)" in type_findings[0].detail
    assert "TEXT" in type_findings[0].detail
