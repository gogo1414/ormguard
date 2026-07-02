"""Unit tests for opt-in CHECK-constraint and enum validation."""

from __future__ import annotations

from ormguard._schema import CheckConstraintInfo, ColumnInfo, TableInfo
from ormguard.config import Config
from ormguard.diff import diff_schemas
from ormguard.model import CHECK_EXTRA, CHECK_MISSING, ENUM_MISMATCH


def _table(columns=None, checks=None):
    t = TableInfo(name="t", schema=None)
    for c in columns or []:
        t.columns[c.name] = c
    for ck in checks or []:
        t.checks[ck.name] = ck
    return t


def _enum_col(values):
    return ColumnInfo(name="status", type_str="VARCHAR(20)", nullable=True, enum_values=values)


def _diff(expected, actual, **cfg_kwargs):
    key = (None, "t")
    cfg = Config(flag_extra_columns=False, **cfg_kwargs)
    return diff_schemas({key: expected}, {key: actual}, cfg)


# ---- enums ---------------------------------------------------------------

def test_enum_mismatch_detected():
    exp = _table([_enum_col(("active", "inactive", "pending"))])
    act = _table([_enum_col(("active", "inactive"))])
    findings = _diff(exp, act, check_enums=True)
    enum = [f for f in findings if f.kind == ENUM_MISMATCH]
    assert len(enum) == 1
    assert enum[0].column == "status"
    assert "pending" in enum[0].detail  # value missing in DB is named


def test_enum_order_does_not_matter():
    exp = _table([_enum_col(("a", "b", "c"))])
    act = _table([_enum_col(("c", "a", "b"))])
    assert not _diff(exp, act, check_enums=True)


def test_enum_check_is_opt_in():
    exp = _table([_enum_col(("a", "b"))])
    act = _table([_enum_col(("a",))])
    assert not _diff(exp, act)  # check_enums defaults off


def test_enum_skipped_when_one_side_missing_values():
    # DB side has no reflected enum values (e.g. SQLite stores enums as VARCHAR).
    exp = _table([_enum_col(("a", "b"))])
    act = _table([ColumnInfo(name="status", type_str="VARCHAR(20)", nullable=True)])
    assert not _diff(exp, act, check_enums=True)


# ---- check constraints ---------------------------------------------------

def test_check_missing_and_extra():
    exp = _table(checks=[CheckConstraintInfo("ck_age_positive")])
    act = _table(checks=[CheckConstraintInfo("ck_price_nonneg")])
    findings = _diff(exp, act, check_constraints=True)
    kinds = {(f.kind) for f in findings}
    assert CHECK_MISSING in kinds  # ck_age_positive declared in ORM, absent in DB
    assert CHECK_EXTRA in kinds    # ck_price_nonneg in DB, not in ORM


def test_check_constraints_opt_in():
    exp = _table(checks=[CheckConstraintInfo("ck_x")])
    act = _table()
    assert not _diff(exp, act)  # check_constraints defaults off


def test_matching_check_names_produce_nothing():
    exp = _table(checks=[CheckConstraintInfo("ck_same")])
    act = _table(checks=[CheckConstraintInfo("ck_same")])
    assert not _diff(exp, act, check_constraints=True)
