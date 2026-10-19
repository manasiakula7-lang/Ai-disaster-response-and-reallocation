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
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session as DBSession

from backend.app import insights, sim
from backend.app.db import get_db
from backend.app.models import Allocation, Artifact

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


# ------------------------------------------------------------ dashboard pages
_ARTIFACT_CACHE = {}


def _artifact(db, key):
    # Normally loaded into the artifacts table by backend.app.load. If the database predates that
    # table (load not re-run after an update), build the same data from the result files instead.
    try:
        a = db.get(Artifact, key)
        if a is not None:
            return a.data
    except ProgrammingError:
        db.rollback()
    if not _ARTIFACT_CACHE:
        _ARTIFACT_CACHE.update(insights.build_artifacts())
    if key not in _ARTIFACT_CACHE:
        raise HTTPException(503, f"'{key}' not available; run python -m backend.app.load")
    return _ARTIFACT_CACHE[key]


def _road_changes(db, upto_day):
    return q(db, """SELECT r.edge_id, r.status, r.travel_time_hr FROM road_events r
                    WHERE r.day <= :day ORDER BY r.day, r.id""", day=upto_day)


@app.get("/graph", summary="District graph for a day: GAT severity, embeddings, attention, road status, centres")
def graph(day: int = Query(3, ge=1, le=7), db: DBSession = Depends(get_db)):
    g = _artifact(db, "graph")
    sev = {r["district"]: r for r in severity(day, None, db)}
    status = {}
    for e in _road_changes(db, day):
        status[e["edge_id"]] = e["status"]
    att = g["attention"].get(str(day), {})
    emb = g["embeddings"].get(str(day), {})
    hosts = {}
    for c in g["centres"]:
        hosts.setdefault(c["district"], []).append(c["centre_id"])
    nodes = [n | {"severity": sev[n["district"]]["severity"], "severity_class": sev[n["district"]]["severity_class"],
                  "embedding": emb.get(n["district"]), "centres": hosts.get(n["district"], [])} for n in g["nodes"]]
    edges = [e | {"status": status.get(e["edge_id"], "open"),
                  "attention": round((att.get(f"{e['source']}|{e['target']}", 0) +
                                      att.get(f"{e['target']}|{e['source']}", 0)) / 2, 4)} for e in g["edges"]]
    return {"day": day, "nodes": nodes, "edges": edges, "centres": g["centres"]}


@app.get("/analytics", summary="Model results for Steps 1-6 (NLP, GAT, MAPPO, federated learning)")
def analytics(db: DBSession = Depends(get_db)):
    return _artifact(db, "analytics")


@app.get("/decisions", summary="Crisis reports the reallocation loop acted on (Step 6), newest first per day")
def decisions(day: Optional[int] = Day, db: DBSession = Depends(get_db)):
    return q(db, """SELECT e.day, e.time, e.district, r.tweet_id, r.category, r.confidence, r.urgency,
                           r.resources, r.text
                    FROM events e JOIN reports r ON r.tweet_id = e.tweet_id
                    WHERE e.run_id = 'step6' AND e.type = 'report' AND (CAST(:day AS INTEGER) IS NULL OR e.day = :day)
                    ORDER BY e.day, r.urgency DESC""", day=day)


@app.get("/decision/{tweet_id}", summary="Why the system sent what it sent after one crisis report")
def decision(tweet_id: str, db: DBSession = Depends(get_db)):
    found = q(db, """SELECT e.day, e.time, e.district, r.* FROM events e JOIN reports r ON r.tweet_id = e.tweet_id
                     WHERE e.run_id = 'step6' AND e.type = 'report' AND e.tweet_id = :t""", t=tweet_id)
    if not found:
        raise HTTPException(404, "report not used by the reallocation loop")
    rep = found[0]
    day, dist = rep["day"], rep["district"]
    wave = insights.next_wave(rep["time"])
    asked = insights.report_resources(rep["resources"] or "")
    sev = next(r for r in severity(day, None, db) if r["district"] == dist)
    dem = demand(day, dist, db)[0]
    wave_ship = q(db, """SELECT centre, resource, round(sum(amount)::numeric, 1)::float AS amount FROM allocations
                         WHERE run_id = 'step6' AND day = :d AND wave = :w AND district = :dist
                         GROUP BY centre, resource ORDER BY centre, resource""", d=day, w=wave, dist=dist)
    # drop rounding dust: less than a tenth of a truckload (or of a rescue team)
    wave_ship = [s for s in wave_ship if s["amount"] >= insights.MIN_SHIPMENT[s["resource"]]]
    day_ship = {r["resource"]: r["amount"] for r in allocations(day, None, "step6", "district", db)
                if r["district"] == dist}
    g = _artifact(db, "graph")
    edges = g["edges"]
    reach = insights.travel(edges, _road_changes(db, day), dist)
    home = {c["centre_id"]: c for c in g["centres"]}
    for s in wave_ship:
        c = home[s["centre"]]
        t, hops = reach.get(c["district"], (None, None))
        s |= {"centre_name": c["name"], "centre_district": c["district"],
              "travel_time_hr": None if t is None else round(t, 2), "hops": hops}
    per_d = _artifact(db, "analytics")["per_district"]
    compare = {name: v.get(dist) for name, v in per_d.items()}
    alerts_after = [e for e in events(day, "alert", "step6", db) if e["district"] == dist and e["time"] >= rep["time"]]
    return {"report": rep | {"text": insights.clean_text(rep["text"])}, "wave": wave, "asked": asked,
            "severity": sev, "demand": dem,
            "planned_today": {r: day_ship.get(r, 0.0) for r in sim.RESOURCES},
            "shipments": wave_ship, "week_coverage_by_policy": compare, "alerts": alerts_after,
            "neighbours": sorted({e["target"] if e["source"] == dist else e["source"]
                                  for e in edges if dist in (e["source"], e["target"])})}


class EvalRequest(BaseModel):
    policy: str = Field("mappo", description="|".join(sim.POLICIES))
    baseline: str = Field("lp_rationed", description="|".join(sim.POLICIES))
    closed_edges: list[int] = []
    stock_factor: float = Field(1.0, gt=0, le=5)
    demand_factor: float = Field(1.0, gt=0, le=5)


@app.post("/evaluate", summary="Play the week with a strategy and a baseline: totals per resource, district and day")
def evaluate(req: EvalRequest):
    for p in (req.policy, req.baseline):
        if p not in sim.POLICIES:
            raise HTTPException(422, f"policy must be one of {list(sim.POLICIES)}")
    return insights.evaluate(sim.Session, req.policy, req.baseline, req.closed_edges,
                             req.stock_factor, req.demand_factor)
