"""Fleet-first multi-tenant validation.

The real multi-tenant world is "1 ORM (possibly several Bases) ↔ N tenant DBs
that each have a different target". ``validate_many`` only does N engines against
a *single shared* target; ``validate_fleet`` lets every tenant declare its own
engine **and** its own set of Bases, then reuses the label × finding matrix and
divergence report to surface "column present on armorfit, absent on larosee".
"""

from __future__ import annotations

from .config import Config
from .core import validate
from .matrix import find_divergence, format_tenant_matrix
from .model import ValidationReport


def validate_fleet(
    fleet: dict[str, object],
    config: Config | None = None,
) -> dict[str, ValidationReport]:
    """Validate a fleet of tenants, each with its own engine and Base(s).

    ``fleet`` maps a tenant label to ``(engine, bases)`` where ``bases`` is a
    declarative Base / MetaData or a list of them (a list is merged by
    ``validate``). Returns ``{label: ValidationReport}`` — pair with
    :func:`format_tenant_matrix` / :func:`find_divergence` for the cross-tenant
    matrix.
    """
    reports: dict[str, ValidationReport] = {}
    for label, spec in fleet.items():
        engine, bases = spec
        reports[label] = validate(engine, bases, config, label=label)
    return reports


__all__ = ["validate_fleet", "format_tenant_matrix", "find_divergence"]
