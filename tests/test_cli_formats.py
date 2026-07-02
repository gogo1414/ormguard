"""`--format` / `--baseline` on the replay and check subcommands.

The live (v1) CLI already supports machine-readable output and baselines; these
tests cover the same flags on `ormguard replay` and `--format` on
`ormguard check`, so CI can emit SARIF / JSON with no database at all.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("alembic")

from ormguard.cli import main  # noqa: E402

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

MODELS = '''
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base
Base = declarative_base()
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    order = Column("order", Integer, nullable=True)
'''


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "0001_init.py").write_text(textwrap.dedent(MIG_0001))
    (versions / "0002_branch.py").write_text(textwrap.dedent(MIG_0002))
    (tmp_path / "fmt_models.py").write_text(textwrap.dedent(MODELS))
    (tmp_path / "ormguard.toml").write_text(textwrap.dedent('''
        pythonpath = ["."]

        [[target]]
        name = "service"
        mode = "replay"
        metadata = "fmt_models:Base"
        migrations = "versions"
        tenants = [["cafe24", "shop_a"], ["larosee", "larosee_co_kr"]]
    '''))
    return tmp_path


def _replay_args(project: Path, *extra: str) -> list[str]:
    return [
        "replay",
        "--migrations", str(project / "versions"),
        "--metadata", "fmt_models:Base",
        "--pythonpath", str(project),
        *extra,
    ]


# -- replay --format -----------------------------------------------------------

def test_replay_format_json_multi_tenant(project, capsys):
    rc = main(_replay_args(
        project, "--tenant", "cafe24:shop_a", "--tenant", "larosee:larosee_co_kr",
        "--format", "json",
    ))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1  # larosee is missing "order"
    assert payload["summary"]["errors"] == 1
    labels = {f["label"] for f in payload["findings"]}
    assert labels == {"larosee_co_kr"}


def test_replay_format_sarif_single_tenant(project, capsys):
    rc = main(_replay_args(project, "--tenant", "larosee:larosee_co_kr", "--format", "sarif"))
    sarif = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert sarif["version"] == "2.1.0"
    results = sarif["runs"][0]["results"]
    assert results and results[0]["ruleId"] == "column_missing"


def test_replay_format_github(project, capsys):
    rc = main(_replay_args(project, "--tenant", "larosee:larosee_co_kr", "--format", "github"))
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out and "users.order" in out


# -- replay --baseline ---------------------------------------------------------

def test_replay_baseline_ratchet(project, capsys):
    baseline = project / "baseline.json"
    # 1) snapshot the known drift
    rc = main(_replay_args(
        project, "--tenant", "cafe24:shop_a", "--tenant", "larosee:larosee_co_kr",
        "--baseline", str(baseline), "--write-baseline",
    ))
    assert rc == 0
    accepted = json.loads(baseline.read_text())["accepted"]
    assert any("larosee_co_kr ::" in fp for fp in accepted)  # label-scoped

    # 2) same drift is now accepted -> exit 0
    capsys.readouterr()
    rc = main(_replay_args(
        project, "--tenant", "cafe24:shop_a", "--tenant", "larosee:larosee_co_kr",
        "--baseline", str(baseline),
    ))
    assert rc == 0


def test_replay_write_baseline_requires_path(project):
    with pytest.raises(SystemExit):
        main(_replay_args(project, "--write-baseline"))


# -- check --format ------------------------------------------------------------

def test_check_format_json_combined(project, capsys):
    rc = main(["check", "--config", str(project / "ormguard.toml"), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    labels = {f["label"] for f in payload["findings"]}
    assert labels == {"service:larosee_co_kr"}  # target-qualified label


def test_check_format_sarif(project, capsys):
    rc = main(["check", "--config", str(project / "ormguard.toml"), "--format", "sarif"])
    sarif = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert sarif["runs"][0]["results"][0]["properties"]["label"] == "service:larosee_co_kr"
