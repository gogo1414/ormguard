# Review style guide for ormguard

When reviewing pull requests, focus on:

- **Correctness of schema comparison** — reflection (`reflect.py`) and diff
  logic (`diff.py`) are the core. Watch for false positives/negatives in
  `column_missing`, `nullable_mismatch`, and `type_mismatch`.
- **SQLAlchemy compatibility** — code must work on SQLAlchemy 1.4 and 2.0, and
  on Python 3.9–3.12. Flag 2.0-only or 3.10+-only usage.
- **Dialect sensitivity** — type comparisons differ per backend (SQLite,
  PostgreSQL, MySQL). Type checks should stay opt-in and conservative.
- **Public API stability** — anything exported from `ormguard/__init__.py` is
  public. Breaking changes need a changelog entry and a version bump.
- **Tests** — behavior changes need tests; prefer the default SQLite path so
  they run without an external database.

Keep comments high-signal. Skip minor style nits that `ruff` already enforces.
Be concise and cite the file/line.
