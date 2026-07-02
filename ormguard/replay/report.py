"""Tenant × finding matrix and divergence reporting for multi-tenant replay.

The implementation now lives in :mod:`ormguard.matrix` (it is not replay-specific
— live fleet runs use it too). Re-exported here for backward compatibility.
"""

from __future__ import annotations

from ..matrix import find_divergence, format_tenant_matrix

__all__ = ["format_tenant_matrix", "find_divergence"]
