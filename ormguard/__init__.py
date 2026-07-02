"""ormguard — fail-fast schema validation for SQLAlchemy.

Brings Hibernate's ``ddl-auto=validate`` to SQLAlchemy: at startup, reflect the
connected database and check that it matches your ORM entities. Catch
entity↔DB drift at boot instead of as a runtime ``column does not exist``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .config import Config
from .core import (
    assert_schema,
    format_matrix,
    validate,
    validate_many,
)
from .fleet import (
    column_analysis,
    format_column_analysis,
    reflect_fleet,
    validate_fleet,
)
from .matrix import find_divergence, format_tenant_matrix
from .model import (
    Finding,
    SchemaValidationError,
    Severity,
    ValidationReport,
)
from .output import github_annotations, to_json, to_sarif

try:
    __version__ = _pkg_version("ormguard")
except PackageNotFoundError:  # source tree without installed metadata
    __version__ = "0.0.0+unknown"

__all__ = [
    "validate",
    "assert_schema",
    "validate_many",
    "validate_fleet",
    "reflect_fleet",
    "column_analysis",
    "format_column_analysis",
    "format_matrix",
    "format_tenant_matrix",
    "find_divergence",
    "to_json",
    "to_sarif",
    "github_annotations",
    "Config",
    "Severity",
    "Finding",
    "ValidationReport",
    "SchemaValidationError",
    "__version__",
]
