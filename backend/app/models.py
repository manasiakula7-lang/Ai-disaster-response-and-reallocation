"""Database tables. Geometries are stored in WGS84 (SRID 4326) with PostGIS."""
from geoalchemy2 import Geometry
from sqlalchemy import Column, Float, Integer, String, Text
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
