"""Real-world validation runner for aace-api — run on a machine that has the
aace-api source, its virtualenv, and network access to a tenant database.

This script only *reads* aace-api (imports its entities); it never modifies it.

Usage (from the aace-api repo root, with ormguard installed in that venv):

    pip install -e /path/to/ormguard
    export TENANT_DB_URL="postgresql://user:pass@host:5432/larosee_co_kr"
    python /path/to/ormguard/examples/validate_aace_tenant.py

Exit code 1 if ERROR-level drift is found (CI-friendly). With the audit doc as
ground truth, you should expect it to flag e.g.
``aivelabs_sv.campaign_sets.campaign_group_id`` as column_missing.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys

from sqlalchemy import create_engine

from ormguard import Config, validate


def _import_all_entities(package_name: str = "src") -> None:
    """Import every submodule so all entities register on Base.metadata —
    mirrors aace-api's own migration/env.py:import_all_modules()."""
    package = importlib.import_module(package_name)
    for _, name, _ in pkgutil.walk_packages(package.__path__, package_name + "."):
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - keep going; some modules need runtime ctx
            print(f"  (skipped import {name}: {exc.__class__.__name__})", file=sys.stderr)


def main() -> int:
    url = os.environ.get("TENANT_DB_URL")
    if not url:
        print("Set TENANT_DB_URL to a tenant database URL.", file=sys.stderr)
        return 2

    _import_all_entities("src")
    # aace-api's declarative Base:
    from src.core.database.agent.database_agent import Base  # type: ignore

    schema = os.environ.get("ORMGUARD_SCHEMA", "aivelabs_sv")
    config = Config(
        schemas={schema} if schema else None,
        ignore_tables={"alembic_version"},
        # ETL-owned tables are populated by aace-etl, not the ORM — ignore the
        # ones you know are intentionally unmapped to cut noise, e.g.:
        # ignore_tables={"alembic_version", "channel_master", "purchase_master"},
    )

    engine = create_engine(url)
    report = validate(engine, Base, config, label=engine.url.database)
    print(report.format_text())
    return 1 if report.has_errors() else 0


if __name__ == "__main__":
    sys.exit(main())
