# Contributing to ormguard

Thanks for your interest in improving ormguard! This project is small and
welcomes issues and pull requests.

## Development setup

```bash
git clone https://github.com/gogo1414/ormguard.git
cd ormguard
python -m pip install -e ".[dev]"
```

## Everyday commands

```bash
pytest                      # unit tests (in-memory SQLite, no external DB)
ruff check .                # lint
python -m ormguard --selfcheck   # end-to-end smoke test against SQLite drift
```

Postgres integration tests are opt-in (they need a real database):

```bash
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/db"
pytest -m postgres
```

### Optional: pre-commit

```bash
pip install pre-commit
pre-commit install          # runs ruff + selfcheck on every commit
```

## Pull request workflow

1. Branch from `main` (`feat/...`, `fix/...`, `chore/...`).
2. Make the change with tests. Keep the public API in `ormguard/__init__.py` stable.
3. Add an entry to `CHANGELOG.md` under **Unreleased**.
4. Open a PR — the template checklist covers tests, lint, and changelog.
5. CI (Python 3.9–3.12 + Postgres integration) must pass before merge.

Direct pushes to `main` are avoided; everything goes through a PR.

## Versioning & releases

Versions come from git tags via `hatch-vcs` — there is **no version string to
edit by hand**. To cut a release:

```bash
git tag v0.2.0
git push origin v0.2.0
```

The `Release` workflow builds the package and publishes it to PyPI via Trusted
Publishing. We follow [Semantic Versioning](https://semver.org/).
