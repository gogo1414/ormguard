"""v2 M4: tenant × finding matrix, divergence report, unparsed-SQL flagging,
and the ``ormguard replay`` CLI.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

pytest.importorskip("alembic")

from ormguard.cli import main, parse_tenant  # noqa: E402
from ormguard.model import UNPARSED_SQL, Severity  # noqa: E402
from ormguard.replay import (  # noqa: E402
    find_divergence,
    format_tenant_matrix,
    validate_migrations,
    validate_tenants,
)

MIG_0001 = '''
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
    )
'''

# Same branching shape as aace migrations: only cafe24 tenants get "order".
MIG_0002 = '''
from alembic import op, context
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
def upgrade():
    platform_type = context.get_x_argument(as_dictionary=True).get("platform_type")
    if platform_type == "cafe24":
        op.add_column("users", sa.Column("order", sa.Integer(), nullable=True))
'''

MIG_UNPARSED = '''
from alembic import op
revision = "0003"
down_revision = "0002"
def upgrade():
    op.execute("CREATE OPERATOR FAMILY weird USING btree")
'''


def _base_expecting_order():
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String(255), nullable=False)
        order = Column("order", Integer, nullable=True)

    return Base


@pytest.fixture()
def migrations_dir(tmp_path: Path) -> Path:
    d = tmp_path / "versions"
    d.mkdir()
    (d / "0001_init.py").write_text(textwrap.dedent(MIG_0001))
    (d / "0002_branch.py").write_text(textwrap.dedent(MIG_0002))
    return d


TENANTS = [("cafe24", "shop_a"), ("cafe24", "shop_b"), ("larosee", "larosee_co_kr")]


# -- matrix / divergence -----------------------------------------------------

def test_matrix_marks_only_drifted_tenants(migrations_dir):
    reports = validate_tenants(_base_expecting_order(), migrations_dir, TENANTS)
    matrix = format_tenant_matrix(reports)
    # one row for the missing column, columns per tenant
    assert "column_missing @ users.order" in matrix
    assert "shop_a" in matrix and "larosee_co_kr" in matrix
    # summary lines
    assert "OK" in matrix
    assert "1 error(s)" in matrix
    # divergence section: finding hits a strict subset (larosee only)
    assert "tenant divergence" in matrix
    assert "only on: larosee_co_kr" in matrix


def test_matrix_all_ok(migrations_dir):
    reports = validate_tenants(
        _base_expecting_order(), migrations_dir, [("cafe24", "shop_a"), ("cafe24", "shop_b")]
    )
    matrix = format_tenant_matrix(reports)
    assert matrix.count("OK") == 2
    assert "tenant divergence" not in matrix


def test_find_divergence_subset_only(migrations_dir):
    reports = validate_tenants(_base_expecting_order(), migrations_dir, TENANTS)
    diverged = find_divergence(reports)
    assert diverged == {"column_missing @ users.order": ["larosee_co_kr"]}


def test_find_divergence_excludes_systematic_drift(migrations_dir):
    # ORM expects a column NO tenant has -> systematic, not divergence.
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String(255), nullable=False)
        never_migrated = Column(Integer, nullable=True)

    reports = validate_tenants(Base, migrations_dir, [("cafe24", "a"), ("cafe24", "b")])
    assert find_divergence(reports) == {}
    assert "column_missing @ users.never_migrated" in format_tenant_matrix(reports)


# -- unparsed SQL flagging -----------------------------------------------------

def test_unparsed_sql_is_flagged(migrations_dir):
    pytest.importorskip("sqlglot")
    (migrations_dir / "0003_weird.py").write_text(textwrap.dedent(MIG_UNPARSED))
    report = validate_migrations(
        _base_expecting_order(), migrations_dir, platform_type="cafe24", database_name="shop_a"
    )
    kinds = {f.kind for f in report.findings}
    assert UNPARSED_SQL in kinds
    unparsed = [f for f in report.findings if f.kind == UNPARSED_SQL]
    assert unparsed[0].severity == Severity.WARN
    assert "CREATE OPERATOR" in unparsed[0].detail


# -- CLI: ormguard replay ------------------------------------------------------

def _write_models(tmp_path: Path) -> None:
    (tmp_path / "m4_models.py").write_text(textwrap.dedent('''
        from sqlalchemy import Column, Integer, String
        from sqlalchemy.orm import declarative_base
        Base = declarative_base()
        class User(Base):
            __tablename__ = "users"
            id = Column(Integer, primary_key=True)
            email = Column(String(255), nullable=False)
            order = Column("order", Integer, nullable=True)
    '''))


def test_cli_replay_multi_tenant_matrix(migrations_dir, tmp_path, capsys):
    _write_models(tmp_path)
    rc = main([
        "replay",
        "--migrations", str(migrations_dir),
        "--metadata", "m4_models:Base",
        "--pythonpath", str(tmp_path),
        "--tenant", "cafe24:shop_a",
        "--tenant", "larosee:larosee_co_kr",
    ])
    out = capsys.readouterr().out
    assert rc == 1  # larosee is missing "order"
    assert "column_missing @ users.order" in out
    assert "only on: larosee_co_kr" in out


def test_cli_replay_single_tenant_ok(migrations_dir, tmp_path, capsys):
    _write_models(tmp_path)
    rc = main([
        "replay",
        "--migrations", str(migrations_dir),
        "--metadata", "m4_models:Base",
        "--pythonpath", str(tmp_path),
        "--tenant", "cafe24:shop_a",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_cli_replay_warn_only_exits_zero(migrations_dir, tmp_path):
    _write_models(tmp_path)
    rc = main([
        "replay",
        "--migrations", str(migrations_dir),
        "--metadata", "m4_models:Base",
        "--pythonpath", str(tmp_path),
        "--tenant", "larosee:larosee_co_kr",
        "--warn-only",
    ])
    assert rc == 0


def test_cli_replay_tenants_file(migrations_dir, tmp_path, capsys):
    _write_models(tmp_path)
    tenants_file = tmp_path / "tenants.json"
    tenants_file.write_text(json.dumps([
        ["cafe24", "shop_a"],
        {"platform_type": "larosee", "database_name": "larosee_co_kr"},
    ]))
    rc = main([
        "replay",
        "--migrations", str(migrations_dir),
        "--metadata", "m4_models:Base",
        "--pythonpath", str(tmp_path),
        "--tenants-file", str(tenants_file),
    ])
    out = capsys.readouterr().out
    assert rc == 1
    assert "shop_a" in out and "larosee_co_kr" in out


def test_parse_tenant_forms():
    assert parse_tenant("cafe24:shop_a") == ("cafe24", "shop_a")
    assert parse_tenant("shop_a") == (None, "shop_a")
    assert parse_tenant(":shop_a") == (None, "shop_a")
