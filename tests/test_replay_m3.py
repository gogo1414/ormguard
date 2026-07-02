"""v2 M3: raw-SQL DDL parsing for op.execute (sqlglot).

Migrations that mutate schema via raw SQL — including DO $$ blocks — must be
reflected in the replayed catalog. Unparseable SQL must surface in
catalog.unparsed. Requires alembic + sqlglot; skipped otherwise.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

pytest.importorskip("alembic")
pytest.importorskip("sqlglot")

from ormguard.replay import replay_migrations, validate_migrations  # noqa: E402
from ormguard.model import COLUMN_MISSING, Severity  # noqa: E402

# Raw SQL for every op we support, plus a DO block and an ignored INSERT.
MIG = '''
from alembic import op
revision = "0001"
down_revision = None
def upgrade():
    op.execute("""
        CREATE TABLE s.campaign_sets (id INTEGER PRIMARY KEY, set_name VARCHAR(255));
        ALTER TABLE s.campaign_sets ADD COLUMN campaign_group_id VARCHAR NOT NULL;
        ALTER TABLE s.campaign_sets ADD COLUMN is_group_added BOOLEAN NOT NULL;
        ALTER TABLE s.campaign_sets DROP COLUMN set_name;
        ALTER TABLE s.campaign_sets ALTER COLUMN campaign_group_id DROP NOT NULL;
        ALTER TABLE s.campaign_sets RENAME COLUMN is_group_added TO group_added;
        INSERT INTO s.campaign_sets (id) VALUES (1);
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE s.campaign_sets ADD COLUMN IF NOT EXISTS soft_deleted BOOLEAN;
        END $$;
    """)
'''

MIG_UNPARSED = '''
from alembic import op
revision = "0001"
down_revision = None
def upgrade():
    op.execute("CREATE OR REPLACE FUNCTION weird() RETURNS void AS $x$ BEGIN END $x$ LANGUAGE plpgsql;")
'''


def _write(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "versions"
    d.mkdir(exist_ok=True)
    (d / "0001_raw.py").write_text(textwrap.dedent(body))
    return d


def test_raw_sql_ddl_applied(tmp_path):
    cat = replay_migrations(_write(tmp_path, MIG))
    t = cat.tables[("s", "campaign_sets")]
    cols = set(t.columns)
    assert "campaign_group_id" in cols            # ADD COLUMN
    assert "set_name" not in cols                  # DROP COLUMN
    assert "is_group_added" not in cols            # renamed away
    assert "group_added" in cols                   # RENAME COLUMN target
    assert "soft_deleted" in cols                   # added inside DO $$ block
    assert t.columns["campaign_group_id"].nullable is True   # ALTER ... DROP NOT NULL
    assert t.columns["group_added"].nullable is False        # was NOT NULL on add


def test_validate_detects_missing_when_migration_never_adds(tmp_path):
    # Migration builds campaign_sets WITHOUT campaign_group_id -> ORM expects it.
    body = '''
from alembic import op
revision = "0001"
down_revision = None
def upgrade():
    op.execute("CREATE TABLE s.campaign_sets (id INTEGER PRIMARY KEY);")
'''
    d = _write(tmp_path, body)
    Base = declarative_base()

    class CampaignSet(Base):
        __tablename__ = "campaign_sets"
        __table_args__ = {"schema": "s"}
        id = Column(Integer, primary_key=True)
        campaign_group_id = Column(String, nullable=False)

    report = validate_migrations(Base, d)
    hit = [f for f in report.findings if f.kind == COLUMN_MISSING and f.column == "campaign_group_id"]
    assert hit and hit[0].severity == Severity.ERROR


def test_alter_column_type_applied(tmp_path):
    body = '''
from alembic import op
revision = "0001"
down_revision = None
def upgrade():
    op.execute("""
        CREATE TABLE s.t (id INTEGER PRIMARY KEY, code VARCHAR(10));
        ALTER TABLE s.t ALTER COLUMN code TYPE INTEGER;
    """)
'''
    cat = replay_migrations(_write(tmp_path, body))
    col = cat.tables[("s", "t")].columns["code"]
    assert "INT" in col.type_str  # VARCHAR(10) -> INTEGER, not left as VARCHAR
    assert "VARCHAR" not in col.type_str


def test_unparseable_sql_surfaces_in_unparsed(tmp_path):
    cat = replay_migrations(_write(tmp_path, MIG_UNPARSED))
    assert cat.unparsed  # function definition could not be interpreted -> surfaced
