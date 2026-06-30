"""Minimal example: fail-fast schema validation on FastAPI startup.

Run a DB that matches `Base` and the app boots; introduce drift and it refuses
to start (strict=True). Requires `fastapi` and `uvicorn` to actually serve.
"""

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

from ormguard.integrations.fastapi import schema_guard_lifespan

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)


engine = create_engine("sqlite:///./example.db")
Base.metadata.create_all(engine)  # for the demo; real apps use Alembic

try:
    from fastapi import FastAPI

    app = FastAPI(lifespan=schema_guard_lifespan(engine, Base, strict=True))

    @app.get("/")
    def root():
        return {"status": "schema validated at startup"}
except ImportError:  # pragma: no cover
    # FastAPI not installed — fall back to a plain assertion so the example
    # still demonstrates the core check.
    from ormguard import assert_schema

    assert_schema(engine, Base, strict=True)
    print("ormguard: schema OK")
