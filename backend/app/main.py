"""FastAPI backend for the disaster-response dashboard (Step 7).

Run from the repo root:
    uvicorn backend.app.main:app --reload
Interactive docs: http://localhost:8000/docs
"""
import json
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from backend.app import sim
from backend.app.db import get_db
from backend.app.models import Allocation

app = FastAPI(title="AI Disaster Response API",
              description="Kerala 2018 floods: districts, relief centres, roads, demand, "
                          "crisis reports, allocations, simulation and what-if analysis.",
              version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

Day = Query(None, ge=1, le=7, description="Scenario day (1 = 18 Aug 2018)")


def feature_collection(rows, geom_key="geometry"):
    feats = []
    for r in rows:
        props = {k: v for k, v in r.items() if k != geom_key}
        feats.append({"type": "Feature", "geometry": json.loads(r[geom_key]), "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def q(db, sql, **params):
    return [dict(r._mapping) for r in db.execute(text(sql), params)]


@app.get("/health")
def health(db: DBSession = Depends(get_db)):
    return {"status": "ok", "postgis": db.execute(text("SELECT postgis_version()")).scalar()}


# ------------------------------------------------------------------ geography
@app.get("/districts", summary="District boundaries (GeoJSON) with severity and demand for a day")
def districts(day: Optional[int] = Day, simplify: float = 0.002, db: DBSession = Depends(get_db)):
    rows = q(db, """
        SELECT d.name, d.population, d.vulnerability, d.flood_exposure_100yr,
               ST_Y(d.hq) AS hq_lat, ST_X(d.hq) AS hq_lon,
               s.severity, s.severity_class,
               m.displaced_people, m.food_kits, m.water_litres, m.medicine_kits, m.rescue_teams,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(d.geom, :tol), 5) AS geometry
        FROM districts d
        LEFT JOIN severity s ON s.district = d.name AND s.day = :day
        LEFT JOIN demand m ON m.district = d.name AND m.day = :day
        ORDER BY d.node_id""", day=day or 1, tol=simplify)
    return feature_collection(rows)


@app.get("/districts/locate", summary="Which district contains a point (PostGIS ST_Contains)")
def locate(lat: float, lon: float, db: DBSession = Depends(get_db)):
    rows = q(db, """SELECT name FROM districts
                    WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))""", lat=lat, lon=lon)
    if not rows:
        raise HTTPException(404, "point is not inside any Kerala district")
    return rows[0]


@app.get("/centres", summary="Relief centres (GeoJSON points) with starting stock")
def centres(db: DBSession = Depends(get_db)):
    return feature_collection(q(db, """
        SELECT centre_id, name, district, food_kits, water_litres, medicine_kits, rescue_teams,
               vehicles, capacity_people, ST_AsGeoJSON(geom) AS geometry FROM centres ORDER BY centre_id"""))


@app.get("/centres/nearest", summary="Nearest relief centres to a point, straight-line km")
def nearest_centres(lat: float, lon: float, k: int = Query(3, ge=1, le=19), db: DBSession = Depends(get_db)):
    return q(db, """
        SELECT centre_id, name, district,
               round((ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)
                      / 1000)::numeric, 1) AS distance_km
        FROM centres ORDER BY geom::geography <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
        LIMIT :k""", lat=lat, lon=lon, k=k)


@app.get("/roads", summary="Road links (GeoJSON) with their status on a day")
def roads(day: Optional[int] = Day, db: DBSession = Depends(get_db)):
    rows = q(db, """SELECT edge_id, source, target, distance_km, travel_time_hr,
                           ST_AsGeoJSON(geom) AS geometry FROM roads ORDER BY edge_id""")
    state = {r["edge_id"]: ("open", r["travel_time_hr"]) for r in rows}
    for e in q(db, "SELECT day, edge_id, status, travel_time_hr FROM road_events WHERE day <= :d ORDER BY day, id",
               d=day or 1):
        base = next(r["travel_time_hr"] for r in rows if r["edge_id"] == e["edge_id"])
        state[e["edge_id"]] = {"blocked": ("blocked", None), "slowed": ("slowed", e["travel_time_hr"])}.get(
            e["status"], ("open", base))
    for r in rows:
        r["status"], r["current_travel_time_hr"] = state[r["edge_id"]]
    return feature_collection(rows)


# ----------------------------------------------------------------- data tables
@app.get("/demand", summary="Simulated demand per district")
def demand(day: Optional[int] = Day, district: Optional[str] = None, db: DBSession = Depends(get_db)):
    return q(db, """SELECT day, district, displaced_people, food_kits, water_litres, medicine_kits, rescue_teams
                    FROM demand WHERE (CAST(:day AS INTEGER) IS NULL OR day = :day) AND (CAST(:dist AS TEXT) IS NULL OR district = :dist)
                    ORDER BY day, district""", day=day, dist=district)


@app.get("/severity", summary="GAT severity per district (Step 2)")
def severity(day: Optional[int] = Day, date: Optional[str] = None, db: DBSession = Depends(get_db)):
    return q(db, """SELECT date, day, district, severity, severity_class FROM severity
                    WHERE (CAST(:day AS INTEGER) IS NULL OR day = :day) AND (CAST(:date AS TEXT) IS NULL OR date = :date)
                    ORDER BY date, district""", day=day, date=date)


@app.get("/reports", summary="Classified crisis tweets (Step 1)")
def reports(date: Optional[str] = None, district: Optional[str] = None, actionable: Optional[bool] = None,
            limit: int = Query(100, le=1000), db: DBSession = Depends(get_db)):
    return q(db, """SELECT tweet_id, posted_utc, date, category, confidence, district, resources, urgency,
                           actionable, text FROM reports
                    WHERE (CAST(:date AS TEXT) IS NULL OR date = :date) AND (CAST(:dist AS TEXT) IS NULL OR district = :dist)
                      AND (CAST(:act AS INTEGER) IS NULL OR actionable = CAST(:act AS INTEGER))
                    ORDER BY urgency DESC LIMIT :lim""",
             date=date, dist=district, act=None if actionable is None else int(actionable), lim=limit)


@app.get("/events", summary="Reallocation loop event log (Step 6)")
def events(day: Optional[int] = Day, type: Optional[str] = None, run_id: str = "step6",
           db: DBSession = Depends(get_db)):
    return q(db, """SELECT day, time, type, district, detail, tweet_id FROM events
                    WHERE run_id = :run AND (CAST(:day AS INTEGER) IS NULL OR day = :day) AND (CAST(:type AS TEXT) IS NULL OR type = :type)
                    ORDER BY day, time, id""", run=run_id, day=day, type=type)


@app.get("/alerts", summary="Alerts only (shortcut for /events?type=alert)")
def alerts(day: Optional[int] = Day, db: DBSession = Depends(get_db)):
    return events(day, "alert", "step6", db)


@app.get("/allocations", summary="Planned shipments; group_by=district|centre|resource totals them")
def allocations(day: Optional[int] = Day, wave: Optional[str] = None, run_id: str = "step6",
                group_by: Optional[str] = Query(None, pattern="^(district|centre|resource)$"),
                db: DBSession = Depends(get_db)):
    where = "run_id = :run AND (CAST(:day AS INTEGER) IS NULL OR day = :day) AND (CAST(:wave AS TEXT) IS NULL OR wave = :wave)"
    if group_by:
        return q(db, f"""SELECT {group_by}, resource, round(sum(amount)::numeric, 1) AS amount
                         FROM allocations WHERE {where} GROUP BY {group_by}, resource
                         ORDER BY {group_by}, resource""", run=run_id, day=day, wave=wave)
    return q(db, f"""SELECT day, wave, centre, district, resource, amount FROM allocations
                     WHERE {where} ORDER BY day, wave, centre, district""", run=run_id, day=day, wave=wave)


@app.get("/metrics", summary="Results tables from Steps 3-6")
def metrics(step: Optional[str] = Query(None, pattern="^[3-6]$"), db: DBSession = Depends(get_db)):
    return q(db, """SELECT step, policy, evaluation, fulfilment, vuln_weighted_fulfilment,
                           worst_district_fulfilment, gini, avg_delay_hr, neglect_district_days
                    FROM metrics WHERE (CAST(:step AS TEXT) IS NULL OR step = :step) ORDER BY step, id""", step=step)


# ------------------------------------------------------------ simulation
class SimRequest(BaseModel):
    policy: str = Field("mappo", description="|".join(sim.POLICIES))
    seed: Optional[int] = Field(None, description="None = official week; any int = a random flood week")
    closed_edges: list[int] = []
    stock_factor: float = Field(1.0, gt=0, le=5)
    demand_factor: float = Field(1.0, gt=0, le=5)


def _check(req):
    if req.policy not in sim.POLICIES:
        raise HTTPException(422, f"policy must be one of {list(sim.POLICIES)}")


@app.get("/policies")
def policies():
    return list(sim.POLICIES)


@app.post("/simulate", summary="Start a 7-day simulation session")
def simulate_start(req: SimRequest):
    _check(req)
    s = sim.Session(req.policy, req.seed, req.closed_edges, req.stock_factor, req.demand_factor)
    sim.SESSIONS[s.id] = s
    return s.state()


def _session(session_id):
    if session_id not in sim.SESSIONS:
        raise HTTPException(404, "unknown session")
    return sim.SESSIONS[session_id]


@app.get("/simulate/{session_id}")
def simulate_state(session_id: str):
    return _session(session_id).state()


@app.post("/simulate/{session_id}/step", summary="Play the next day; shipments are saved to the database")
def simulate_step(session_id: str, db: DBSession = Depends(get_db)):
    s = _session(session_id)
    try:
        day = s.step()
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.bulk_insert_mappings(Allocation, [{"run_id": s.id, "day": day["day"], "wave": "day", **x}
                                         for x in day["shipments"]])
    db.commit()
    return day | {"state": s.state()}


class CloseRoad(BaseModel):
    edge_id: int


@app.post("/simulate/{session_id}/close_road", summary="Close a road from today to the end of the week")
def simulate_close_road(session_id: str, body: CloseRoad):
    s = _session(session_id)
    if s.done:
        raise HTTPException(409, "week already finished")
    if not any(int(e["edge_id"]) == body.edge_id for e in s.env.edges):
        raise HTTPException(404, "unknown edge_id")
    s.env.close_road(body.edge_id)
    s.obs = s.env.observe()
    return s.state()


@app.post("/whatif", summary="Play a week with changes and compare with the unchanged week")
def whatif(req: SimRequest):
    _check(req)
    return sim.what_if(req.policy, req.seed, req.closed_edges, req.stock_factor, req.demand_factor)
