"""v2 M2: tenant-aware replay.

Migrations branch on ``op.get_bind().engine.url.database`` (mall_id) and
``context.get_x_argument()["platform_type"]`` — the exact pattern aace-api uses.
Replaying the same migration set with different tenant profiles must produce
different schemas. No database required.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

pytest.importorskip("alembic")

from ormguard import format_matrix  # noqa: E402
from ormguard.replay import replay_migrations, validate_tenants  # noqa: E402

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

# Branches exactly like aace: enterprise DB early-returns; cafe24 gets "order";
# the larosee database gets "rfm".
MIG_0002 = '''
from alembic import op, context
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
def upgrade():
    database_name = op.get_bind().engine.url.database
    if database_name in ("hmall",):
        return
    platform_type = context.get_x_argument(as_dictionary=True).get("platform_type")
    if platform_type == "cafe24":
        op.add_column("users", sa.Column("order", sa.Integer(), nullable=True))
    if database_name == "larosee_co_kr":
        op.add_column("users", sa.Column("rfm", sa.Integer(), nullable=True))
'''


@pytest.fixture()
def migrations_dir(tmp_path: Path) -> Path:
    d = tmp_path / "versions"
    d.mkdir()
    (d / "0001_init.py").write_text(textwrap.dedent(MIG_0001))
    (d / "0002_branch.py").write_text(textwrap.dedent(MIG_0002))
    return d


def _cols(catalog):
    return set(catalog.tables[(None, "users")].columns)


def test_cafe24_gets_order_only(migrations_dir):
    cat = replay_migrations(migrations_dir, platform_type="cafe24", database_name="cafe24shop")
    assert _cols(cat) == {"id", "email", "order"}


def test_larosee_gets_rfm_only(migrations_dir):
    cat = replay_migrations(migrations_dir, platform_type="larosee", database_name="larosee_co_kr")
    assert _cols(cat) == {"id", "email", "rfm"}


def test_hmall_early_returns(migrations_dir):
    cat = replay_migrations(migrations_dir, platform_type="hmall", database_name="hmall")
    assert _cols(cat) == {"id", "email"}


def test_validate_tenants_matrix(migrations_dir):
    # ORM expects the cafe24 shape (id, email, order). larosee/hmall diverge.
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String(255), nullable=False)
        order = Column("order", Integer, nullable=True)

    tenants = [("cafe24", "cafe24shop"), ("larosee", "larosee_co_kr"), ("hmall", "hmall")]
    reports = validate_tenants(Base, migrations_dir, tenants)

    assert reports["cafe24shop"].ok                      # matches ORM
    assert not reports["larosee_co_kr"].ok               # missing "order"
    assert not reports["hmall"].ok                       # missing "order"
    # matrix renders one line per tenant
    matrix = format_matrix(reports)
    assert "cafe24shop" in matrix and "larosee_co_kr" in matrix


def test_duplicate_database_name_raises(migrations_dir):
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String(255), nullable=False)

    # Two tenants sharing a database_name would collide in the keyed result.
    tenants = [("cafe24", "shop"), ("larosee", "shop")]
    with pytest.raises(ValueError, match="duplicate database_name"):
        validate_tenants(Base, migrations_dir, tenants)
