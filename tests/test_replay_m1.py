"""v2 M1: offline migration replay into an in-memory catalog.

Generates a small migration set in a temp dir, replays it without any database,
and checks both the resulting catalog and the ORM diff. Requires `alembic`
(migrations do `from alembic import op`); skipped if it isn't installed.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

pytest.importorskip("alembic")

from ormguard.model import COLUMN_MISSING, Severity  # noqa: E402
from ormguard.replay import replay_migrations, validate_migrations  # noqa: E402
from ormguard.replay.loader import order_migrations  # noqa: E402

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
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
    )
'''

MIG_0002 = '''
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
def upgrade():
    op.add_column("users", sa.Column("nickname", sa.String(50), nullable=False))
    op.alter_column("users", "email", nullable=True)
'''

MIG_0003 = '''
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
def upgrade():
    op.drop_table("orders")
'''


@pytest.fixture()
def migrations_dir(tmp_path: Path) -> Path:
    d = tmp_path / "versions"
    d.mkdir()
    (d / "0001_init.py").write_text(textwrap.dedent(MIG_0001))
    (d / "0002_users.py").write_text(textwrap.dedent(MIG_0002))
    (d / "0003_drop_orders.py").write_text(textwrap.dedent(MIG_0003))
    return d


def test_replay_builds_final_catalog(migrations_dir):
    catalog = replay_migrations(migrations_dir)

    users = catalog.tables[(None, "users")]
    assert set(users.columns) == {"id", "email", "nickname"}
    assert users.columns["email"].nullable is True       # altered in 0002
    assert users.columns["nickname"].nullable is False
    assert (None, "orders") not in catalog.tables         # dropped in 0003


def _orm_base():
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String(255), nullable=True)
        nickname = Column(String(50), nullable=False)

    return Base


def test_validate_migrations_matches_orm(migrations_dir):
    report = validate_migrations(_orm_base(), migrations_dir)
    assert report.ok, report.format_text()


def test_validate_migrations_detects_orm_only_column(migrations_dir):
    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        email = Column(String(255), nullable=True)
        nickname = Column(String(50), nullable=False)
        phone = Column(String(20), nullable=False)  # no migration ever adds this

    report = validate_migrations(Base, migrations_dir)
    missing = [f for f in report.findings if f.kind == COLUMN_MISSING and f.column == "phone"]
    assert missing and missing[0].severity == Severity.ERROR
    assert report.has_errors()


def test_dangling_down_revision_raises():
    class M:
        def __init__(self, rev, down):
            self.revision = rev
            self.down_revision = down
            self.upgrade = lambda: None

    # "B" points at "A", but "A" was never loaded -> broken chain, not a root.
    mods = {"B": M("B", "A"), "C": M("C", "B")}
    with pytest.raises(ValueError, match="unknown down_revision"):
        order_migrations(mods)


BATCH_MIG = '''
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
def upgrade():
    op.create_table("t", sa.Column("id", sa.Integer(), primary_key=True))
    with op.batch_alter_table("t") as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(10), nullable=False))
        batch_op.create_unique_constraint("uq_t_code", ["code"])
        batch_op.create_check_constraint("ck_t_code", "code <> ''")
'''


def test_batch_constraint_ops_do_not_crash(tmp_path: Path):
    d = tmp_path / "versions"
    d.mkdir()
    (d / "0001_batch.py").write_text(textwrap.dedent(BATCH_MIG))
    catalog = replay_migrations(d)
    # The batch constraint calls are accepted; the column change still applies.
    assert set(catalog.tables[(None, "t")].columns) == {"id", "code"}


ENUM_MIG = '''
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
def upgrade():
    op.create_table(
        "t",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.Enum("active", "inactive", name="status_enum"),
                  server_default="active", nullable=False),
    )
'''


def test_replay_preserves_enum_and_server_default(tmp_path: Path):
    d = tmp_path / "versions"
    d.mkdir()
    (d / "0001_enum.py").write_text(textwrap.dedent(ENUM_MIG))
    col = replay_migrations(d).tables[(None, "t")].columns["status"]
    assert col.enum_values == ("active", "inactive")
    assert col.has_server_default is True


def test_topo_order_handles_branch_and_merge():
    # Diamond: A -> {B, C} -> D(merge). Build fake modules.
    class M:
        def __init__(self, rev, down):
            self.revision = rev
            self.down_revision = down
            self.upgrade = lambda: None

    mods = {
        "A": M("A", None),
        "B": M("B", "A"),
        "C": M("C", "A"),
        "D": M("D", ("B", "C")),
    }
    ordered = [m.revision for m in order_migrations(mods)]
    assert ordered.index("A") < ordered.index("B")
    assert ordered.index("A") < ordered.index("C")
    assert ordered.index("B") < ordered.index("D")
    assert ordered.index("C") < ordered.index("D")
