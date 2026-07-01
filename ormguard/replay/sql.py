"""Parse raw SQL from ``op.execute(...)`` and apply its DDL to the catalog (M3).

Uses sqlglot (PostgreSQL dialect). Handles CREATE/DROP TABLE and
ALTER TABLE ADD/DROP/ALTER/RENAME COLUMN, including ``DO $$ ... $$`` blocks
(best-effort: DDL statements inside the block are extracted and applied). Pure
DML (INSERT/UPDATE/DELETE) has no schema effect and is ignored. Anything that
cannot be interpreted is appended to ``catalog.unparsed`` — never silently
dropped, so reports never claim a false "clean".
"""

from __future__ import annotations

import re

from .._schema import ColumnInfo, TableInfo

try:
    import sqlglot
    from sqlglot import exp
    _SQLGLOT_ERR = None
except Exception as exc:  # pragma: no cover - sqlglot is an optional extra
    sqlglot = None
    exp = None
    _SQLGLOT_ERR = exc

# DO $tag$ ... $tag$  (tag may be empty: $$ ... $$)
_DO_RE = re.compile(r"DO\s+\$([A-Za-z0-9_]*)\$(.*?)\$\1\$", re.IGNORECASE | re.DOTALL)
# DDL statements inside a PL/pgSQL body (sqlglot can't parse the whole block).
_DDL_IN_BODY = re.compile(
    r"(?:ALTER\s+TABLE|CREATE\s+TABLE|DROP\s+TABLE)[\s\S]*?;", re.IGNORECASE
)

# Statement types with no effect on column presence/shape — safe to skip
# without flagging. Everything else that we can't apply goes to `unparsed`.
_SCHEMA_IRRELEVANT = (
    (exp.Insert, exp.Update, exp.Delete, exp.Select, exp.Merge, exp.Set, exp.Comment)
    if exp is not None
    else ()
)


def apply_sql(catalog, sql: str, *, default_schema: str | None = None) -> None:
    """Apply the DDL in ``sql`` to ``catalog``. Records anything unhandled in
    ``catalog.unparsed``."""
    if sqlglot is None:  # optional dep missing
        catalog.unparsed.append(str(sql))
        return

    remainder, do_bodies = _split_do(str(sql))
    for body in do_bodies:
        found = False
        for m in _DDL_IN_BODY.finditer(body):
            found = True
            _parse_and_apply(catalog, m.group(0), default_schema)
        if not found and body.strip():
            catalog.unparsed.append(body.strip())
    _parse_and_apply(catalog, remainder, default_schema)


def _split_do(sql: str):
    bodies: list[str] = []

    def repl(match):
        bodies.append(match.group(2))
        return ""

    remainder = _DO_RE.sub(repl, sql)
    return remainder, bodies


def _parse_and_apply(catalog, sql_text: str, default_schema: str | None) -> None:
    sql_text = sql_text.strip()
    if not sql_text:
        return
    try:
        statements = sqlglot.parse(sql_text, read="postgres")
    except Exception:
        catalog.unparsed.append(sql_text)
        return
    for stmt in statements:
        if stmt is None:
            continue
        try:
            handled = _apply_stmt(catalog, stmt, default_schema)
        except Exception:
            handled = False
        if not handled and not isinstance(stmt, _SCHEMA_IRRELEVANT):
            # Unhandled DDL *and* statements sqlglot only recognized as a bare
            # Command (unsupported syntax) — flag rather than silently drop.
            catalog.unparsed.append(stmt.sql(dialect="postgres"))


def _table_ref(stmt, default_schema):
    t = stmt.find(exp.Table)
    if t is None:
        return (default_schema, None)
    return (t.db or default_schema, t.name)


def _coldef_to_info(cdef) -> ColumnInfo:
    dtype = cdef.args.get("kind")
    type_str = dtype.sql(dialect="postgres").upper() if dtype is not None else ""
    cons = {type(c.args["kind"]).__name__ for c in cdef.args.get("constraints") or []}
    return ColumnInfo(
        name=cdef.name,
        type_str=type_str,
        nullable="NotNullColumnConstraint" not in cons,
        primary_key="PrimaryKeyColumnConstraint" in cons,
    )


def _apply_stmt(catalog, stmt, default_schema) -> bool:
    kind = (stmt.args.get("kind") or "").upper() if hasattr(stmt, "args") else ""

    if isinstance(stmt, exp.Create) and kind == "TABLE":
        schema, table = _table_ref(stmt, default_schema)
        if table is None:
            return False
        info = TableInfo(name=table, schema=schema)
        for cdef in stmt.this.expressions:
            if isinstance(cdef, exp.ColumnDef):
                ci = _coldef_to_info(cdef)
                info.columns[ci.name] = ci
        catalog.tables[(schema, table)] = info
        return True

    if isinstance(stmt, exp.Drop) and kind == "TABLE":
        schema, table = _table_ref(stmt, default_schema)
        if table is None:
            return False
        catalog.drop_table(table, schema=schema)
        return True

    if isinstance(stmt, exp.Alter):
        schema, table = _table_ref(stmt, default_schema)
        if table is None:
            return False
        for action in stmt.args.get("actions") or []:
            _apply_action(catalog, table, schema, action)
        return True

    return False


def _apply_action(catalog, table, schema, action) -> None:
    if isinstance(action, exp.ColumnDef):  # ADD COLUMN [IF NOT EXISTS]
        ci = _coldef_to_info(action)
        info = catalog.tables.get((schema, table))
        if info is not None:
            info.columns[ci.name] = ci
    elif isinstance(action, exp.Drop) and (action.args.get("kind") or "").upper() == "COLUMN":
        col = action.name or (action.this.name if action.this is not None else None)
        if col:
            catalog.drop_column(table, col, schema=schema)
    elif isinstance(action, exp.AlterColumn):
        allow_null = action.args.get("allow_null")
        if allow_null is not None:
            catalog.alter_column(table, action.name, nullable=bool(allow_null), schema=schema)
    elif isinstance(action, exp.RenameColumn):
        new = action.args.get("to")
        if new is not None:
            catalog.alter_column(table, action.this.name, new_column_name=new.name, schema=schema)
