"""Database tables. Geometries are stored in WGS84 (SRID 4326) with PostGIS."""
from geoalchemy2 import Geometry
from sqlalchemy import JSON, Column, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class District(Base):
    __tablename__ = "districts"
    name = Column(String, primary_key=True)
    node_id = Column(Integer, unique=True)
    population = Column(Integer)
    vulnerability = Column(Float)
    flood_exposure_100yr = Column(Float)
    hq = Column(Geometry("POINT", srid=4326))
    geom = Column(Geometry("MULTIPOLYGON", srid=4326))


class Centre(Base):
    __tablename__ = "centres"
    centre_id = Column(String, primary_key=True)
    name = Column(String)
    district = Column(String, index=True)
    food_kits = Column(Float)
    water_litres = Column(Float)
    medicine_kits = Column(Float)
    rescue_teams = Column(Float)
    vehicles = Column(Integer)
    capacity_people = Column(Integer)
    geom = Column(Geometry("POINT", srid=4326))


class Road(Base):
    __tablename__ = "roads"
    edge_id = Column(Integer, primary_key=True)
    source = Column(String)
    target = Column(String)
    distance_km = Column(Float)
    travel_time_hr = Column(Float)
    geom = Column(Geometry("LINESTRING", srid=4326))   # straight line HQ to HQ (estimated roads)


class RoadEvent(Base):
    __tablename__ = "road_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, index=True)
    edge_id = Column(Integer, index=True)
    status = Column(String)            # blocked / slowed / open
    travel_time_hr = Column(Float, nullable=True)


class Demand(Base):
    __tablename__ = "demand"
    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Integer, index=True)
    district = Column(String, index=True)
    displaced_people = Column(Integer)
    food_kits = Column(Float)
    water_litres = Column(Float)
    medicine_kits = Column(Float)
    rescue_teams = Column(Float)


class Severity(Base):
    __tablename__ = "severity"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, index=True)
    day = Column(Integer, index=True, nullable=True)   # scenario day (1 = 18 Aug 2018)
    district = Column(String, index=True)
    severity = Column(Float)
    severity_class = Column(String)


class Report(Base):
    __tablename__ = "reports"
    tweet_id = Column(String, primary_key=True)
    posted_utc = Column(String)
    date = Column(String, index=True)
    category = Column(String)
    confidence = Column(Float)
    district = Column(String, index=True, nullable=True)
    resources = Column(String)
    urgency = Column(Float)
    actionable = Column(Integer)
    text = Column(Text)


class Event(Base):
    """Step 6 event log: reports, road changes, dispatches, alerts."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, index=True)
    day = Column(Integer, index=True)
    time = Column(String)
    type = Column(String, index=True)
    district = Column(String)
    detail = Column(Text)
    tweet_id = Column(String)


class Allocation(Base):
    """Shipments: from the Step 6 run (run_id='step6') or from API simulations."""
    __tablename__ = "allocations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, index=True)
    day = Column(Integer, index=True)
    wave = Column(String)
    centre = Column(String)
    district = Column(String)
    resource = Column(String)
    amount = Column(Float)


class Metric(Base):
    """Results tables from Steps 3-6."""
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    step = Column(String, index=True)
    policy = Column(String)
    evaluation = Column(String)
    fulfilment = Column(Float)
    vuln_weighted_fulfilment = Column(Float)
    worst_district_fulfilment = Column(Float)
    gini = Column(Float)
    avg_delay_hr = Column(Float)
    neglect_district_days = Column(Float)


class Artifact(Base):
    """Precomputed JSON for the dashboard (graph + GAT embeddings, model analytics)."""
    __tablename__ = "artifacts"
    key = Column(String, primary_key=True)
    data = Column(JSON)


# Operations desk logs (backend/app/ops.py). Created on API start-up if missing and kept by the
# loader, so the operator's history survives a reload of the scenario data.
class OpsLog(Base):
    __tablename__ = "ops_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)
    seq = Column(Integer)
    day = Column(Integer, index=True)
    time = Column(String)
    type = Column(String, index=True)
    district = Column(String)
    detail = Column(Text)
    data = Column(JSON)
    logged_at = Column(String)


class OpsOperation(Base):
    __tablename__ = "ops_operations"
    session_id = Column(String, primary_key=True)
    op_id = Column(String, primary_key=True)
    day = Column(Integer, index=True)
    wave = Column(String)
    district = Column(String, index=True)
    centres = Column(JSON)                     # contributing relief centres
    items = Column(JSON)                       # totals per resource
    sources = Column(JSON)                     # per centre: items, hours, route
    hours = Column(Float)
    status = Column(String, index=True)        # in_progress / success / fail
    reason = Column(String)
    note = Column(Text)
    reported_at = Column(String)


class OpsDayReport(Base):
    __tablename__ = "ops_day_reports"
    session_id = Column(String, primary_key=True)
    day = Column(Integer, primary_key=True)
    policy = Column(String)
    need_met = Column(Float)
    worst_need_met = Column(Float)
    gini = Column(Float)
    ops_success_rate = Column(Float)
    report = Column(JSON)
    closed_at = Column(String)


OPS_TABLES = [OpsLog.__table__, OpsOperation.__table__, OpsDayReport.__table__]
