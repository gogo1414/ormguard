"""Command-line interface: ``python -m ormguard``.

Validate a database against ORM metadata in CI. Exit code 1 on ERROR findings.

    python -m ormguard --url postgresql://u:p@host/db --metadata myapp.db:Base --schema aivelabs_sv
"""

from __future__ import annotations

import argparse
import importlib
import sys

from sqlalchemy import create_engine

from .config import Config
from .core import validate


def _force_utf8_output() -> None:
    """Emit UTF-8 even on legacy consoles (e.g. Windows cp949).

    Report output contains characters like ``—`` and ``→``; without this, a
    ``print`` on a cp949 terminal raises ``UnicodeEncodeError``.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - stream may not support it
                pass


def _load_metadata(spec: str):
    """Load 'package.module:attr' where attr is a declarative Base or MetaData."""
    if ":" not in spec:
        raise SystemExit("--metadata must be 'package.module:attr' (e.g. myapp.db:Base)")
    module_name, attr = spec.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(prog="ormguard", description="Validate DB schema against SQLAlchemy ORM.")
    parser.add_argument(
        "--selfcheck", action="store_true",
        help="run a self-contained demo against in-memory SQLite (no --url/--metadata needed)",
    )
    parser.add_argument("--url", help="SQLAlchemy database URL")
    parser.add_argument("--metadata", help="'package.module:attr' (Base or MetaData)")
    parser.add_argument("--schema", action="append", default=None, help="restrict to schema (repeatable)")
    parser.add_argument("--check-types", action="store_true", help="also compare column types")
    parser.add_argument("--no-nullable", action="store_true", help="skip nullable comparison")
    parser.add_argument("--no-extra", action="store_true", help="do not flag DB-only columns")
    parser.add_argument("--ignore-table", action="append", default=[], help="table to skip (repeatable)")
    parser.add_argument(
        "--warn-only", action="store_true",
        help="exit 0 even on errors (report only)",
    )
    args = parser.parse_args(argv)

    if args.selfcheck:
        from .selfcheck import run_selfcheck

        report = run_selfcheck()
        return 1 if (report.has_errors() and not args.warn_only) else 0

    if not args.url or not args.metadata:
        parser.error("--url and --metadata are required (or use --selfcheck)")

    config = Config(
        schemas=set(args.schema) if args.schema else None,
        check_types=args.check_types,
        check_nullable=not args.no_nullable,
        flag_extra_columns=not args.no_extra,
        ignore_tables=set(args.ignore_table),
    )

    target = _load_metadata(args.metadata)
    engine = create_engine(args.url)
    report = validate(engine, target, config)

    print(report.format_text())
    if report.has_errors() and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
