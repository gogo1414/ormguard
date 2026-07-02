"""Load Alembic migration scripts and order them by their revision DAG.

Migrations are imported from file paths (no alembic config needed) and read for
``revision`` / ``down_revision`` / ``branch_labels``. Returns modules ordered
root -> head via topological sort, handling branches and merges (tuple
down_revision).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_module(path: Path) -> ModuleType | None:
    spec = importlib.util.spec_from_file_location(f"_ormguard_mig_{path.stem}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "revision") or not hasattr(module, "upgrade"):
        return None
    return module


def _down_set(module: ModuleType) -> set[str]:
    down = getattr(module, "down_revision", None)
    if down is None:
        return set()
    if isinstance(down, (list, tuple)):
        return {d for d in down if d}
    return {down}


def discover_migrations(migrations_dir: str | Path) -> dict[str, ModuleType]:
    """Map revision id -> module for every migration file in a directory tree."""
    root = Path(migrations_dir)
    modules: dict[str, ModuleType] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.name.startswith("__"):
            continue
        module = _load_module(path)
        if module is not None:
            modules[module.revision] = module
    return modules


def order_migrations(modules: dict[str, ModuleType]) -> list[ModuleType]:
    """Topologically sort revisions root -> head (Kahn's algorithm)."""
    # Build dependency edges, failing loudly on a down_revision we never loaded
    # (a broken chain) rather than silently treating that revision as a root.
    deps: dict[str, set[str]] = {}
    for rev, m in modules.items():
        downs = _down_set(m)
        unknown = {d for d in downs if d not in modules}
        if unknown:
            raise ValueError(
                f"migration {rev!r} references unknown down_revision(s): {sorted(unknown)}"
            )
        deps[rev] = downs
    indegree = {rev: len(d) for rev, d in deps.items()}
    children: dict[str, list[str]] = {rev: [] for rev in modules}
    for rev, ds in deps.items():
        for d in ds:
            children[d].append(rev)

    # Deterministic order: start from roots sorted by revision id.
    ready = sorted([rev for rev, deg in indegree.items() if deg == 0])
    ordered: list[str] = []
    while ready:
        rev = ready.pop(0)
        ordered.append(rev)
        for child in sorted(children[rev]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()

    if len(ordered) != len(modules):
        missing = set(modules) - set(ordered)
        raise ValueError(f"migration DAG has a cycle or broken chain near: {sorted(missing)}")

    return [modules[rev] for rev in ordered]


def load_ordered(migrations_dir: str | Path) -> list[ModuleType]:
    return order_migrations(discover_migrations(migrations_dir))
