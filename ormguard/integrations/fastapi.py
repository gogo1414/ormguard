"""FastAPI integration: validate schema at application startup.

Usage::

    from contextlib import asynccontextmanager
    from ormguard.integrations.fastapi import schema_guard_lifespan

    app = FastAPI(lifespan=schema_guard_lifespan(engine, Base, strict=True))

In ``strict`` mode a mismatch raises and the app refuses to start (the
Hibernate ``validate`` behaviour). In non-strict mode it logs warnings and
serves anyway.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from ..config import Config
from ..core import validate

logger = logging.getLogger("ormguard")


def schema_guard_lifespan(engine, target, *, strict: bool = True, config: Config | None = None):
    """Return a FastAPI ``lifespan`` context manager that validates on startup."""

    @asynccontextmanager
    async def lifespan(app):
        report = validate(engine, target, config)
        if report.findings:
            level = logging.ERROR if (strict and report.has_errors()) else logging.WARNING
            logger.log(level, "schema validation findings:\n%s", report.format_text())
        else:
            logger.info("ormguard: schema OK")
        if strict:
            report.raise_if_errors()
        yield

    return lifespan
