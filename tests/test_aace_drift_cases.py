"""Reproduce the real drift findings from aace-api's manual audit
(`aace-api/docs/alembic_orm_drift_audit.md`) as a self-contained test.

We model the documented entities and a database that is missing the columns the
audit says migrations never created, then assert ormguard reports exactly those.
No aace-api source, private libraries, or Postgres required — runs on SQLite.

Ground-truth findings encoded here (larosee baseline):
  CRITICAL  campaign_sets.campaign_group_id   (String, NOT NULL)  -> never migrated
  CRITICAL  campaign_sets.is_group_added      (Boolean, NOT NULL) -> never migrated
  HIGH      send_reservation.is_purchase      (String, nullable)  -> never migrated
  INFO      campaign_sets.set_name            -> in DB but not mapped by ORM (extra)
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base

from ormguard import validate
from ormguard.model import COLUMN_EXTRA, COLUMN_MISSING, Severity

Base = declarative_base()


class CampaignSet(Base):
    __tablename__ = "campaign_sets"
    id = Column(Integer, primary_key=True)
    # These two are used by the ORM/repository but no migration creates them:
    campaign_group_id = Column(String, nullable=False)
    is_group_added = Column(Boolean, nullable=False)
    # NOTE: 'set_name' deliberately NOT mapped here — it exists in the DB.


class SendReservation(Base):
    __tablename__ = "send_reservation"
    id = Column(Integer, primary_key=True)
    is_purchase = Column(String, nullable=True)  # SELECTed by repo, never migrated


def _migration_produced_db():
    """A database as the migrations actually build it for larosee: campaign_sets
    has set_name but lacks the group columns; send_reservation lacks is_purchase."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE campaign_sets (id INTEGER PRIMARY KEY, set_name VARCHAR(255))"
        ))
        conn.execute(text(
            "CREATE TABLE send_reservation (id INTEGER PRIMARY KEY)"
        ))
    return engine


def test_reproduces_audit_critical_and_high_findings():
    report = validate(_migration_produced_db(), Base)
    by_col = {(f.kind, f.table, f.column): f for f in report.findings}

    # CRITICAL: both campaign group columns flagged as missing, at ERROR severity.
    cg = by_col[(COLUMN_MISSING, "campaign_sets", "campaign_group_id")]
    ig = by_col[(COLUMN_MISSING, "campaign_sets", "is_group_added")]
    assert cg.severity == Severity.ERROR
    assert ig.severity == Severity.ERROR

    # HIGH: is_purchase missing — still ERROR because absence crashes at runtime,
    # regardless of the column being nullable.
    ip = by_col[(COLUMN_MISSING, "send_reservation", "is_purchase")]
    assert ip.severity == Severity.ERROR

    # INFO/extra: set_name exists in DB but is unmapped by the ORM.
    sn = by_col[(COLUMN_EXTRA, "campaign_sets", "set_name")]
    assert sn.severity == Severity.WARN

    # Overall: the run fails (as it should — these broke larosee in production).
    assert report.has_errors()
    assert len(report.errors) == 3
