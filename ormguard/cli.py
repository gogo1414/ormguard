"""Command-line interface: ``python -m ormguard``.

Three modes:

* live validation (default, v1) — reflect a running database and diff it
  against ORM metadata::

      python -m ormguard --url postgresql://u:p@host/db --metadata myapp.db:Base --schema aivelabs_sv

* ``replay`` (v2) — no database: replay Alembic migrations offline per tenant
  profile and diff the computed schema against ORM metadata::

      python -m ormguard replay --migrations migration/versions --metadata myapp.db:Base \\
          --tenant cafe24:cafe24shop --tenant larosee:larosee_co_kr

* ``check`` — run several targets (service DB, warehouse DB, …) from one
  config file::

      python -m ormguard check --config ormguard.toml

Exit code 1 on ERROR findings (unless ``--warn-only``).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

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


def _extend_pythonpath(paths) -> None:
    for p in paths or []:
        resolved = str(Path(p).resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def parse_tenant(spec: str) -> tuple[str | None, str]:
    """'platform:database' -> (platform, database); bare 'database' -> (None, database)."""
    if ":" in spec:
        platform, database = spec.split(":", 1)
        return (platform or None, database)
    return (None, spec)


def load_tenants_file(path: str | Path) -> list[tuple[str | None, str]]:
    """JSON list of ``["platform", "database"]`` pairs or
    ``{"platform_type": ..., "database_name": ...}`` objects."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tenants: list[tuple[str | None, str]] = []
    for entry in data:
        if isinstance(entry, dict):
            tenants.append((entry.get("platform_type"), entry["database_name"]))
        else:
            platform, database = entry
            tenants.append((platform, database))
    return tenants


def _add_check_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--schema", action="append", default=None, help="restrict to schema (repeatable)")
    parser.add_argument("--check-types", action="store_true", help="also compare column types")
    parser.add_argument("--check-indexes", action="store_true", help="also compare indexes (opt-in)")
    parser.add_argument(
        "--check-foreign-keys", action="store_true", help="also compare foreign keys (opt-in)",
    )
    parser.add_argument(
        "--check-defaults", action="store_true",
        help="also compare server-default presence (opt-in)",
    )
    parser.add_argument("--no-nullable", action="store_true", help="skip nullable comparison")
    parser.add_argument("--no-extra", action="store_true", help="do not flag DB-only columns")
    parser.add_argument("--ignore-table", action="append", default=[], help="table to skip (repeatable)")
    parser.add_argument(
        "--warn-only", action="store_true",
        help="exit 0 even on errors (report only)",
    )


def _config_from_args(args) -> Config:
    return Config(
        schemas=set(args.schema) if args.schema else None,
        check_types=args.check_types,
        check_indexes=args.check_indexes,
        check_foreign_keys=args.check_foreign_keys,
        check_server_defaults=args.check_defaults,
        check_nullable=not args.no_nullable,
        flag_extra_columns=not args.no_extra,
        ignore_tables=set(args.ignore_table),
    )


# ---------------------------------------------------------------------------
# replay subcommand (v2)
# ---------------------------------------------------------------------------

def _main_replay(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ormguard replay",
        description="Replay Alembic migrations offline (no database) and diff against ORM metadata.",
    )
    parser.add_argument("--migrations", required=True, help="migrations directory (e.g. migration/versions)")
    parser.add_argument("--metadata", required=True, help="'package.module:attr' (Base or MetaData)")
    parser.add_argument(
        "--tenant", action="append", default=[],
        help="tenant profile as 'platform:database' (repeatable); bare 'database' is allowed",
    )
    parser.add_argument(
        "--tenants-file",
        help="JSON file with tenant profiles: [[platform, database], ...] or "
             "[{'platform_type': ..., 'database_name': ...}, ...]",
    )
    parser.add_argument(
        "--pythonpath", action="append", default=[],
        help="directory to prepend to sys.path before importing --metadata (repeatable)",
    )
    _add_check_flags(parser)
    args = parser.parse_args(argv)

    from .replay import format_tenant_matrix, validate_migrations, validate_tenants

    _extend_pythonpath(args.pythonpath)
    config = _config_from_args(args)
    target = _load_metadata(args.metadata)

    tenants = [parse_tenant(t) for t in args.tenant]
    if args.tenants_file:
        tenants.extend(load_tenants_file(args.tenants_file))

    if len(tenants) > 1:
        reports = validate_tenants(target, args.migrations, tenants, config)
        print(format_tenant_matrix(reports))
        failed = any(r.has_errors() for r in reports.values())
    else:
        platform_type, database_name = tenants[0] if tenants else (None, None)
        report = validate_migrations(
            target, args.migrations, config,
            platform_type=platform_type, database_name=database_name,
        )
        print(report.format_text())
        failed = report.has_errors()

    return 1 if (failed and not args.warn_only) else 0


# ---------------------------------------------------------------------------
# check subcommand (multi-target config file)
# ---------------------------------------------------------------------------

def _main_check(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ormguard check",
        description="Validate every target defined in an ormguard config file (TOML).",
    )
    parser.add_argument("--config", default="ormguard.toml", help="path to config file (default: ormguard.toml)")
    parser.add_argument("--target", action="append", default=[], help="only run this named target (repeatable)")
    parser.add_argument("--warn-only", action="store_true", help="exit 0 even on errors (report only)")
    args = parser.parse_args(argv)

    from .configfile import run_config

    return run_config(args.config, only=args.target or None, warn_only=args.warn_only)


# ---------------------------------------------------------------------------
# default (v1 live validation)
# ---------------------------------------------------------------------------

def _main_live(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ormguard",
        description="Validate DB schema against SQLAlchemy ORM. "
                    "Subcommands: 'replay' (offline migration replay), 'check' (multi-target config).",
    )
    parser.add_argument(
        "--selfcheck", action="store_true",
        help="run a self-contained demo against in-memory SQLite (no --url/--metadata needed)",
    )
    parser.add_argument("--url", help="SQLAlchemy database URL")
    parser.add_argument("--metadata", help="'package.module:attr' (Base or MetaData)")
    _add_check_flags(parser)
    parser.add_argument(
        "--notify-webhook",
        help="POST the report to a Slack/Discord incoming webhook when drift is found",
    )
    parser.add_argument(
        "--notify-on", choices=("error", "any"), default="error",
        help="send the webhook on 'error' findings (default) or on 'any' finding",
    )
    args = parser.parse_args(argv)

    if args.selfcheck:
        from .selfcheck import run_selfcheck

        report = run_selfcheck()
        return 1 if (report.has_errors() and not args.warn_only) else 0

    if not args.url or not args.metadata:
        parser.error("--url and --metadata are required (or use --selfcheck)")

    from sqlalchemy import create_engine

    config = _config_from_args(args)
    target = _load_metadata(args.metadata)
    engine = create_engine(args.url)
    report = validate(engine, target, config)

    print(report.format_text())

    if args.notify_webhook:
        should_notify = report.has_errors() if args.notify_on == "error" else bool(report.findings)
        if should_notify:
            from .notify import notify_webhook

            if not notify_webhook(args.notify_webhook, report):
                print("ormguard: warning — webhook notification failed", file=sys.stderr)

    if report.has_errors() and not args.warn_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if argv and argv[0] == "replay":
        return _main_replay(argv[1:])
    if argv and argv[0] == "check":
        return _main_check(argv[1:])
    return _main_live(argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
