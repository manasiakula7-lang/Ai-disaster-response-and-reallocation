"""Create the tables and load everything Steps 0-6 produced.

Usage (from the repo root, with the database running):
    python -m backend.app.load

Safe to re-run: it drops and recreates the tables.
"""
import csv
from datetime import datetime

import geopandas as gpd
from shapely import force_2d
from shapely.geometry import LineString, MultiPolygon, Point
from sqlalchemy import text

from backend.app.db import SessionLocal, engine
from backend.app.models import (Allocation, Base, Centre, Demand, District, Event, Metric, Report,
                                Road, RoadEvent, Severity)
from ml.env.relief_env import ROOT, SEVERITY_START_DAY

DATA = ROOT / "data"
METRIC_KEYS = ["fulfilment", "vuln_weighted_fulfilment", "worst_district_fulfilment", "gini",
               "avg_delay_hr", "neglect_district_days"]


def rows(path):
    with open(path, newline="", encoding="utf8") as f:
        return list(csv.DictReader(f))


def ewkt(geom):
    return f"SRID=4326;{geom.wkt}"


def scenario_day(date):
    d = (datetime.strptime(date, "%Y-%m-%d") - datetime.strptime(SEVERITY_START_DAY, "%Y-%m-%d")).days + 1
    return d if 1 <= d <= 7 else None


def main():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()

    shapes = gpd.read_file(DATA / "raw/boundaries/KERALA_DISTRICT_BDY.shp").to_crs(4326)
    shapes = {r.DISTRICT: r.geometry for r in shapes.itertuples()}
    hq = {r["district"]: Point(float(r["lon"]), float(r["lat"]))
          for r in rows(DATA / "simulated/district_locations.csv")}
    for r in rows(DATA / "processed/graph_nodes.csv"):
        g = force_2d(shapes[r["district"]])
        g = g if isinstance(g, MultiPolygon) else MultiPolygon([g])
        db.add(District(name=r["district"], node_id=int(r["node_id"]), population=int(r["population_2018"]),
                        vulnerability=float(r["vulnerability_score"]),
                        flood_exposure_100yr=float(r["flood_exposure_100yr"]),
                        hq=ewkt(hq[r["district"]]), geom=ewkt(g)))

    for r in rows(DATA / "simulated/relief_centres.csv"):
        db.add(Centre(centre_id=r["centre_id"], name=r["name"], district=r["district"],
                      food_kits=float(r["food_kits"]), water_litres=float(r["water_litres"]),
                      medicine_kits=float(r["medicine_kits"]), rescue_teams=float(r["rescue_teams"]),
                      vehicles=int(r["vehicles"]), capacity_people=int(r["capacity_people"]),
                      geom=ewkt(Point(float(r["lon"]), float(r["lat"])))))

    for r in rows(DATA / "simulated/road_edges.csv"):
        db.add(Road(edge_id=int(r["edge_id"]), source=r["source"], target=r["target"],
                    distance_km=float(r["distance_km"]), travel_time_hr=float(r["travel_time_hr"]),
                    geom=ewkt(LineString([hq[r["source"]], hq[r["target"]]]))))
    for r in rows(DATA / "simulated/road_events.csv"):
        db.add(RoadEvent(day=int(r["day"]), edge_id=int(r["edge_id"]), status=r["status"],
                         travel_time_hr=float(r["travel_time_hr"]) if r["travel_time_hr"] else None))

    for r in rows(DATA / "simulated/demand_timeline.csv"):
        db.add(Demand(day=int(r["day"]), district=r["district"], displaced_people=int(r["displaced_people"]),
                      **{k: float(r[k]) for k in ("food_kits", "water_litres", "medicine_kits", "rescue_teams")}))
    for r in rows(DATA / "processed/district_severity_daily.csv"):
        db.add(Severity(date=r["date"], day=scenario_day(r["date"]), district=r["district"],
                        severity=float(r["severity"]), severity_class=r["severity_class"]))

    for r in rows(DATA / "processed/crisis_reports.csv"):
        db.add(Report(tweet_id=r["tweet_id"], posted_utc=r["posted_utc"], date=r["date"],
                      category=r["pred_label"], confidence=float(r["pred_confidence"]),
                      district=r["primary_district"] or None, resources=r["resources"],
                      urgency=float(r["urgency"]), actionable=int(r["actionable"]), text=r["text"]))

    res = ROOT / "ml/realloc/results"
    for r in rows(res / "event_log.csv"):
        db.add(Event(run_id="step6", day=int(r["day"]), time=r["time"], type=r["type"],
                     district=r["district"] or None, detail=r["detail"], tweet_id=r["tweet_id"] or None))
    db.bulk_insert_mappings(Allocation, [
        {"run_id": "step6", "day": int(r["day"]), "wave": r["wave"], "centre": r["centre"],
         "district": r["district"], "resource": r["resource"], "amount": float(r["amount"])}
        for r in rows(res / "plans.csv")])

    sources = [("3", ROOT / "ml/baselines/results/baseline_metrics.csv", "official"),
               ("4", ROOT / "ml/marl/results/marl_metrics.csv", "official"),
               ("4", ROOT / "ml/marl/results/test_scenarios.csv", "mean of 50 unseen weeks"),
               ("5", ROOT / "ml/fl/results/fl_metrics.csv", None),
               ("6", res / "realloc_metrics.csv", None)]
    for step, path, evaluation in sources:
        for r in rows(path):
            db.add(Metric(step=step, policy=r.get("policy") or r.get("model"),
                          evaluation=evaluation or r["evaluation"],
                          **{k: float(r[k]) for k in METRIC_KEYS}))
    db.commit()
    for t in Base.metadata.sorted_tables:
        print(f"{t.name:<14} {db.execute(text(f'SELECT count(*) FROM {t.name}')).scalar()}")
    db.close()


if __name__ == "__main__":
    main()
