"""Multi-target config file (``ormguard.toml``) — validate several databases
and migration environments in one run.

Real services rarely have just one schema to guard. A typical split (the one
that motivated this feature) is a *service* database owned by an API plus a
*warehouse* database owned by an ETL pipeline, each with its own declarative
Base and its own Alembic environment. One config file declares every target;
``python -m ormguard check --config ormguard.toml`` validates them all::

    [[target]]
    name = "service"
    mode = "replay"                       # offline: no database needed
    metadata = "src.db:Base"
    migrations = "migration/versions"
    schemas = ["aivelabs_sv"]
    tenants = [["cafe24", "shop_a"], ["larosee", "larosee_co_kr"]]

    [[target]]
    name = "warehouse-mart"
    mode = "live"                         # reflect a running database
    metadata = "src.models.aace_mart:Base"
    url_env = "WAREHOUSE_DB_URL"
    schemas = ["aace_mart"]

Relative paths (``migrations``, ``tenants_file``, ``pythonpath`` entries) are
resolved against the config file's directory, so the file can live at the repo
root and be run from anywhere (including CI).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .model import ValidationReport

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - depends on interpreter
    try:
        import tomli as _toml  # type: ignore[no-redef]
    except ModuleNotFoundError:
        _toml = None


@dataclass
class Target:
    """One validation target parsed from the config file."""

    name: str
    mode: str  # "replay" | "live"
    metadata: str  # 'package.module:attr'
    migrations: str | None = None  # replay mode
    url: str | None = None  # live mode
    url_env: str | None = None  # live mode: read URL from this env var
    tenants: list[tuple[str | None, str]] = field(default_factory=list)
    tenants_file: str | None = None
    pythonpath: list[str] = field(default_factory=list)
    config: Config = field(default_factory=Config)


def _parse_config(data: dict, target: dict) -> Config:
    def opt(key, default):
        return target.get(key, data.get(key, default))

    return Config(
        schemas=set(opt("schemas", None)) if opt("schemas", None) else None,
        ignore_tables=set(opt("ignore_tables", [])),
        ignore_columns=set(opt("ignore_columns", [])),
        check_nullable=bool(opt("check_nullable", True)),
        check_types=bool(opt("check_types", False)),
        check_indexes=bool(opt("check_indexes", False)),
        check_foreign_keys=bool(opt("check_foreign_keys", False)),
        check_server_defaults=bool(opt("check_defaults", False)),
        flag_extra_columns=bool(opt("flag_extra_columns", True)),
    )


def load_targets(path: str | Path) -> list[Target]:
    """Parse ``ormguard.toml`` into a list of :class:`Target`.

    Top-level keys act as defaults; each ``[[target]]`` entry can override them.
    """
    if _toml is None:
        raise SystemExit(
            "ormguard check needs a TOML parser: use Python 3.11+ or `pip install tomli`"
        )
    path = Path(path)
    data = _toml.loads(path.read_text(encoding="utf-8"))

    entries = data.get("target")
    if not entries:
        raise SystemExit(f"{path}: no [[target]] entries found")

    targets: list[Target] = []
    for i, entry in enumerate(entries):
        if "metadata" not in entry:
            raise SystemExit(f"{path}: target #{i + 1} is missing required key 'metadata'")
        mode = entry.get("mode", "replay" if "migrations" in entry else "live")
        if mode not in ("replay", "live"):
            raise SystemExit(f"{path}: target #{i + 1}: mode must be 'replay' or 'live', got {mode!r}")
        tenants = [
            (t[0] or None, t[1]) if isinstance(t, list)
            else (t.get("platform_type"), t["database_name"])
            for t in entry.get("tenants", [])
        ]
        targets.append(
            Target(
                name=entry.get("name", f"target-{i + 1}"),
                mode=mode,
                metadata=entry["metadata"],
                migrations=entry.get("migrations"),
                url=entry.get("url"),
                url_env=entry.get("url_env"),
                tenants=tenants,
                tenants_file=entry.get("tenants_file"),
                pythonpath=entry.get("pythonpath", data.get("pythonpath", [])),
                config=_parse_config(data, entry),
            )
        )
    return targets


def _resolve(base: Path, p: str | None) -> str | None:
    if p is None:
        return None
    candidate = Path(p)
    return str(candidate if candidate.is_absolute() else base / candidate)


def run_target(target: Target, base_dir: Path) -> dict[str, ValidationReport]:
    """Run one target; returns ``{label: ValidationReport}`` (one entry unless
    the target is a multi-tenant replay)."""
    from .cli import _load_metadata, load_tenants_file

    for p in target.pythonpath:
        resolved = _resolve(base_dir, p)
        if resolved not in sys.path:
            sys.path.insert(0, resolved)

    metadata = _load_metadata(target.metadata)

    if target.mode == "replay":
        from .replay import validate_migrations, validate_tenants

        if not target.migrations:
            raise SystemExit(f"target {target.name!r}: replay mode requires 'migrations'")
        migrations = _resolve(base_dir, target.migrations)
        tenants = list(target.tenants)
        if target.tenants_file:
            tenants.extend(load_tenants_file(_resolve(base_dir, target.tenants_file)))
        if len(tenants) > 1:
            return validate_tenants(metadata, migrations, tenants, target.config)
        platform_type, database_name = tenants[0] if tenants else (None, None)
        report = validate_migrations(
            metadata, migrations, target.config,
            platform_type=platform_type, database_name=database_name, label=target.name,
        )
        return {target.name: report}

    # live mode
    from sqlalchemy import create_engine

    from .core import validate

    url = target.url or (os.environ.get(target.url_env) if target.url_env else None)
    if not url:
        raise SystemExit(
            f"target {target.name!r}: live mode requires 'url' or 'url_env'"
            + (f" (env var {target.url_env!r} is not set)" if target.url_env else "")
        )
    engine = create_engine(url)
    return {target.name: validate(engine, metadata, target.config, label=target.name)}


def run_config(
    path: str | Path,
    *,
    only: list[str] | None = None,
    warn_only: bool = False,
    fmt: str = "text",
) -> int:
    """Run every target in the config file and print a combined report.

    ``fmt`` selects the output: ``text`` (per-target sections, default) or one
    combined machine-readable document — ``json`` / ``sarif`` / ``github`` —
    with every report keyed ``<target>`` (or ``<target>:<tenant>`` for
    multi-tenant replay targets).

    Returns the process exit code: 1 if any target has ERROR findings (0 with
    ``warn_only``).
    """
    from .matrix import format_tenant_matrix

    path = Path(path)
    targets = load_targets(path)
    if only:
        unknown = set(only) - {t.name for t in targets}
        if unknown:
            raise SystemExit(f"{path}: unknown target(s): {', '.join(sorted(unknown))}")
        targets = [t for t in targets if t.name in only]

    failed = False
    combined: dict[str, object] = {}
    for target in targets:
        reports = run_target(target, path.parent)
        if fmt == "text":
            print(f"== {target.name} ({target.mode}) ==")
            if len(reports) > 1:
                print(format_tenant_matrix(reports))
            else:
                print(next(iter(reports.values())).format_text())
            print()
        else:
            for label, report in reports.items():
                key = target.name if label == target.name else f"{target.name}:{label}"
                # Re-label with the qualified key so json/sarif/github output
                # keeps the target context, not just the tenant name.
                combined[key] = ValidationReport(findings=report.findings, label=key)
        failed = failed or any(r.has_errors() for r in reports.values())

    if fmt == "json":
        from .output import to_json

        print(to_json(combined))
    elif fmt == "sarif":
        from .output import to_sarif

        print(to_sarif(combined))
    elif fmt == "github":
        from .output import github_annotations

        for line in github_annotations(combined):
            print(line)

    return 1 if (failed and not warn_only) else 0


__all__ = ["Target", "load_targets", "run_target", "run_config"]
