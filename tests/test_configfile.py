"""Multi-target config file (`ormguard check --config ormguard.toml`).

Models the aace-api / aace-etl split: a service DB (replay, multi-tenant) and a
warehouse DB (live SQLite here) validated in one run.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("alembic")

from ormguard.cli import main  # noqa: E402
from ormguard.configfile import load_targets  # noqa: E402

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

SERVICE_MODELS = '''
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
Base = declarative_base()
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
'''

WAREHOUSE_MODELS = '''
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base
Base = declarative_base()
class Fact(Base):
    __tablename__ = "facts"
    id = Column(Integer, primary_key=True)
    metric = Column(String(64), nullable=False)

def make_db(path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
'''


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A miniature two-database project: service (replay) + warehouse (live)."""
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "0001_init.py").write_text(textwrap.dedent(MIG_0001))
    (tmp_path / "svc_models.py").write_text(textwrap.dedent(SERVICE_MODELS))
    (tmp_path / "wh_models.py").write_text(textwrap.dedent(WAREHOUSE_MODELS))

    # build the "live" warehouse database
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        import wh_models

        wh_models.make_db(tmp_path / "warehouse.db")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("wh_models", None)

    (tmp_path / "ormguard.toml").write_text(textwrap.dedent(f'''
        pythonpath = ["."]

        [[target]]
        name = "service"
        mode = "replay"
        metadata = "svc_models:Base"
        migrations = "versions"
        tenants = [["cafe24", "shop_a"], ["larosee", "larosee_co_kr"]]

        [[target]]
        name = "warehouse"
        mode = "live"
        metadata = "wh_models:Base"
        url = "sqlite:///{(tmp_path / 'warehouse.db').as_posix()}"
    '''))
    return tmp_path


def test_load_targets(project):
    targets = load_targets(project / "ormguard.toml")
    assert [t.name for t in targets] == ["service", "warehouse"]
    service, warehouse = targets
    assert service.mode == "replay"
    assert service.tenants == [("cafe24", "shop_a"), ("larosee", "larosee_co_kr")]
    assert warehouse.mode == "live"
    assert warehouse.url.startswith("sqlite:///")


def test_check_runs_all_targets_ok(project, capsys):
    rc = main(["check", "--config", str(project / "ormguard.toml")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "== service (replay) ==" in out
    assert "== warehouse (live) ==" in out


def test_check_fails_on_drift(project, capsys):
    # ORM gains a column no migration creates -> replay target must fail.
    (project / "svc_models.py").write_text(textwrap.dedent(SERVICE_MODELS).replace(
        'email = Column(String(255), nullable=False)',
        'email = Column(String(255), nullable=False)\n    phone = Column(String(20))',
    ))
    import sys

    sys.modules.pop("svc_models", None)
    rc = main(["check", "--config", str(project / "ormguard.toml")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "column_missing @ users.phone" in out
    sys.modules.pop("svc_models", None)


def test_check_target_filter(project, capsys):
    rc = main(["check", "--config", str(project / "ormguard.toml"), "--target", "warehouse"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "warehouse" in out
    assert "== service" not in out


def test_check_unknown_target_errors(project):
    with pytest.raises(SystemExit):
        main(["check", "--config", str(project / "ormguard.toml"), "--target", "nope"])


def test_missing_metadata_key_errors(tmp_path):
    (tmp_path / "bad.toml").write_text('[[target]]\nname = "x"\n')
    with pytest.raises(SystemExit):
        load_targets(tmp_path / "bad.toml")
