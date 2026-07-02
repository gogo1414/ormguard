"""Fleet-first multi-tenant validation.

The real multi-tenant world is "1 ORM (possibly several Bases) ↔ N tenant DBs
that each have a different target". ``validate_many`` only does N engines against
a *single shared* target; ``validate_fleet`` lets every tenant declare its own
engine **and** its own set of Bases, then reuses the label × finding matrix and
divergence report to surface "column present on armorfit, absent on larosee".
"""

from __future__ import annotations

from sqlalchemy import MetaData

from .config import Config
from .core import validate
from .matrix import find_divergence, format_tenant_matrix
from .model import ValidationReport


def _merge_metadata(bases) -> MetaData:
    """Union one-or-more declarative Bases / MetaData into a single MetaData.

    ``bases`` may be a single Base/MetaData or an iterable of them. Tables are
    copied into a fresh MetaData; a name already present (same schema) wins
    first-seen and later duplicates are skipped.
    """
    if isinstance(bases, (list, tuple, set)):
        sources = list(bases)
    else:
        sources = [bases]

    merged = MetaData()
    for src in sources:
        md = getattr(src, "metadata", src)
        for table in md.tables.values():
            if table.key in merged.tables:
                continue
            table.to_metadata(merged)
    return merged


def validate_fleet(
    fleet: dict[str, object],
    config: Config | None = None,
) -> dict[str, ValidationReport]:
    """Validate a fleet of tenants, each with its own engine and Base(s).

    ``fleet`` maps a tenant label to ``(engine, bases)`` where ``bases`` is a
    declarative Base / MetaData or a list of them. Returns
    ``{label: ValidationReport}`` — pair with :func:`format_tenant_matrix` /
    :func:`find_divergence` for the cross-tenant matrix.
    """
    reports: dict[str, ValidationReport] = {}
    for label, spec in fleet.items():
        engine, bases = spec
        merged = _merge_metadata(bases)
        reports[label] = validate(engine, merged, config, label=label)
    return reports


__all__ = ["validate_fleet", "format_tenant_matrix", "find_divergence"]
