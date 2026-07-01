"""Offline Alembic replay (ormguard v2).

Replays migrations into an in-memory catalog without a database, then diffs the
result against ORM metadata. Supports per-tenant branching (platform_type /
database_name). See docs/V2_OFFLINE_REPLAY.md.
"""

from __future__ import annotations

from .catalog import Catalog
from .engine import replay_migrations, validate_migrations, validate_tenants
from .loader import load_ordered
from .report import find_divergence, format_tenant_matrix

__all__ = [
    "Catalog",
    "replay_migrations",
    "validate_migrations",
    "validate_tenants",
    "load_ordered",
    "format_tenant_matrix",
    "find_divergence",
]
