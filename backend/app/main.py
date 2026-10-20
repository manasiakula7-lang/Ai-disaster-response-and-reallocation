"""FastAPI backend for the disaster-response dashboard (Step 7).

Run from the repo root:
    uvicorn backend.app.main:app --reload
Interactive docs: http://localhost:8000/docs
"""
import json
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session as DBSession

from backend.app import insights, live, ops, sim
from backend.app.db import engine, get_db
from backend.app.models import OPS_TABLES, Base, Allocation, Artifact, OpsDayReport, OpsLog, OpsOperation

app = FastAPI(title="AI Disaster Response API",
              description="Kerala 2018 floods: districts, relief centres, roads, demand, "
                          "crisis reports, allocations, simulation and what-if analysis.",
              version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _ops_tables():
    # The operations desk tables are new: create them if the database was loaded before they existed.
    try:
        Base.metadata.create_all(engine, tables=OPS_TABLES)
    except Exception as e:                       # the rest of the API still works without them
        print("could not create ops tables:", e)

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


# ------------------------------------------------------------ live operations
class LiveStart(BaseModel):
    policy: str = Field("mappo", description="mappo | lp_rationed")


class LiveAdvance(BaseModel):
    hours: float = Field(1.0, ge=0, le=200, description="clock hours to move forward")
    until: Optional[str] = Field(None, description="'event' = stop after the next report, road change or wave")


class LiveReport(BaseModel):
    text: str = Field(..., min_length=3, max_length=1000)
    district: Optional[str] = Field(None, description="leave empty to locate the report from its text")


def _live(session_id):
    if session_id not in live.LIVE:
        raise HTTPException(404, "unknown live session; start a new one")
    return live.LIVE[session_id]


@app.post("/live", summary="Start a live session: the official week replayed on a clock")
def live_start(req: LiveStart):
    if req.policy not in ("mappo", "lp_rationed"):
        raise HTTPException(422, "policy must be mappo or lp_rationed")
    s = live.LiveSession(req.policy)
    live.LIVE[s.id] = s
    while len(live.LIVE) > 20:                       # keep memory bounded
        live.LIVE.pop(next(iter(live.LIVE)))
    return {"state": s.state(), "events": s.since(0)}


@app.get("/live/{session_id}", summary="Live state, plus events after `since`")
def live_state(session_id: str, since: int = 0):
    s = _live(session_id)
    return {"state": s.state(), "events": s.since(since)}


@app.post("/live/{session_id}/advance", summary="Move the clock; reports and road changes arrive, waves dispatch")
def live_advance(session_id: str, req: LiveAdvance):
    s = _live(session_id)
    events = s.advance(req.hours, req.until)
    return {"state": s.state(), "events": events}


@app.post("/live/{session_id}/report", summary="Submit a new crisis report; it is read by the NLP and the plan is redone")
def live_report(session_id: str, req: LiveReport):
    s = _live(session_id)
    if req.district and req.district not in s.env.districts:
        raise HTTPException(422, f"unknown district {req.district}")
    try:
        out = s.submit(req.text, req.district)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return out | {"state": s.state()}


@app.post("/analyse", summary="Run the Step 1 NLP on one message (no plan change)")
def analyse_text(req: LiveReport):
    return live.analyse(req.text, req.district)


# ---------------------------------------------------------------- route planning
LOCAL_HR = 1.0     # same as the simulator: delivery inside the centre's own district


def _shortest(rows, src, dst, use_state=True):
    """Dijkstra over the district road links. use_state=False ignores the flood (normal roads)."""
    import heapq
    adj = defaultdict(list)
    for r in rows:
        if use_state and r["status"] == "blocked":
            continue
        t = r["current_travel_time_hr"] if use_state else r["travel_time_hr"]
        adj[r["source"]].append((r["target"], t, r)); adj[r["target"]].append((r["source"], t, r))
    best, prev, heap = {src: 0.0}, {}, [(0.0, src)]
    while heap:
        t, u = heapq.heappop(heap)
        if u == dst:
            break
        if t > best[u]:
            continue
        for v, w, r in adj[u]:
            if t + w < best.get(v, float("inf")):
                best[v], prev[v] = t + w, (u, r)
                heapq.heappush(heap, (t + w, v))
    if dst not in best:
        return None
    legs, node = [], dst
    while node != src:
        u, r = prev[node]
        legs.append({"edge_id": r["edge_id"], "from": u, "to": node, "status": r["status"] if use_state else "open",
                     "hours": round(r["current_travel_time_hr"] if use_state else r["travel_time_hr"], 2),
                     "normal_hours": round(r["travel_time_hr"], 2), "km": r["distance_km"]})
        node = u
    return list(reversed(legs))


@app.get("/route", summary="Fastest open route from a relief centre to a district on a given day")
def route(district: str, day: int = Query(3, ge=1, le=7), centre: Optional[str] = None,
          need: str = Query("rescue_teams", description="when no centre is given, pick the fastest one that has this"),
          db: DBSession = Depends(get_db)):
    """Picks the centre (if not given) and the fastest route over today's road network: blocked links are
    avoided and slowed links count at their slowed travel time. Waypoints are the district HQs on the way,
    so the map can draw the route along real streets."""
    rows = roads(day=day, db=db)["features"]
    rows = [f["properties"] | {"edge_id": f["properties"]["edge_id"]} for f in rows]
    dists = {d["name"]: d for d in (f["properties"] for f in districts(day=day, simplify=0.01, db=db)["features"])}
    if district not in dists:
        raise HTTPException(404, f"unknown district {district}")
    cs = {c["properties"]["centre_id"]: c for c in centres(db=db)["features"]}
    options = []
    for cid, c in cs.items():
        p = c["properties"]
        if centre and cid != centre:
            continue
        if not centre and need in p and not p[need]:
            continue
        legs = [] if p["district"] == district else _shortest(rows, p["district"], district)
        if legs is None:
            options.append({"centre_id": cid, "reachable": False})
            continue
        options.append({"centre_id": cid, "reachable": True, "legs": legs,
                        "hours": round(LOCAL_HR + sum(x["hours"] for x in legs), 2)})
    if centre and centre not in cs:
        raise HTTPException(404, f"unknown centre {centre}")
    reach = sorted((o for o in options if o["reachable"]), key=lambda o: o["hours"])
    if not reach:
        return {"reachable": False, "district": district, "day": day, "centre": centre,
                "detail": f"No open road reaches {district} from {'this centre' if centre else 'any centre'} today."}
    best = reach[0]
    c = cs[best["centre_id"]]
    p = c["properties"]
    normal = [] if p["district"] == district else _shortest(rows, p["district"], district, use_state=False)
    normal_hours = round(LOCAL_HR + sum(x["hours"] for x in normal), 2)
    hq = lambda d: [dists[d]["hq_lat"], dists[d]["hq_lon"]]
    lon, lat = c["geometry"]["coordinates"]
    waypoints = [[lat, lon]] + [hq(x["to"]) for x in best["legs"]]
    if not best["legs"]:
        waypoints.append(hq(district))
    avoided = [r for r in rows if r["status"] == "blocked"]
    return {"reachable": True, "day": day, "district": district,
            "centre": {"centre_id": best["centre_id"], "name": p["name"], "district": p["district"],
                       "rescue_teams": p["rescue_teams"], "vehicles": p["vehicles"]},
            "legs": best["legs"], "hours": best["hours"], "normal_hours": normal_hours,
            "normal_path": [normal[0]["from"]] + [x["to"] for x in normal] if normal else [p["district"]],
            "path": [p["district"]] + [x["to"] for x in best["legs"]],
            "km": round(sum(x["km"] for x in best["legs"]), 1), "waypoints": waypoints,
            "blocked_today": [f"{r['source']} – {r['target']}" for r in avoided],
            "alternatives": [{"centre_id": o["centre_id"], "name": cs[o["centre_id"]]["properties"]["name"],
                              "hours": o["hours"]} for o in reach[1:4]]}


# ---------------------------------------------------------------- operations desk
class OpsStart(BaseModel):
    policy: str = Field("mappo", description="mappo | lp_rationed")


class OpsSupply(BaseModel):
    option: str = Field("none", description="|".join(o["key"] for o in ops.SUPPLY_OPTIONS))
    overrides: dict[str, dict[str, Optional[float]]] = Field(
        {}, description="per centre, e.g. {'RC01': {'food_kits': 5000, 'vehicles': 4}}")


class OpsReport(BaseModel):
    tweet_id: Optional[str] = Field(None, description="a dataset report from /ops/{id}/dataset")
    text: Optional[str] = Field(None, min_length=3, max_length=1000, description="or a typed report")
    district: Optional[str] = None


class OpsOutcome(BaseModel):
    status: str = Field(..., description="success | fail")
    reason: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)


def _ops(session_id):
    if session_id not in ops.OPS:
        raise HTTPException(404, "unknown operations session; start a new one")
    return ops.OPS[session_id]


def _ops_save(db, s):
    """Write new log entries, today's operations and closed-day reports to the ops_* tables."""
    try:
        now = datetime.utcnow().isoformat(timespec="seconds")
        saved = getattr(s, "saved_seq", 0)
        for e in s.since(saved):
            extra = {k: v for k, v in e.items() if k not in ("seq", "day", "time", "type", "district", "detail")}
            db.add(OpsLog(session_id=s.id, seq=e["seq"], day=e["day"], time=e["time"], type=e["type"],
                          district=e["district"], detail=e["detail"], data=extra or None, logged_at=now))
        for o in s.operations[getattr(s, "saved_ops_from", 0):]:
            db.merge(OpsOperation(session_id=s.id, op_id=o["op_id"], day=o["day"], wave=o["wave"], district=o["district"],
                                  centres=o["centres"], items=o["items"], sources=o["sources"], hours=o["hours"],
                                  status=o["status"], reason=o["reason"], note=o["note"], reported_at=o.get("reported_at")))
        for r in s.day_reports[len(getattr(s, "saved_days", [])):]:
            db.merge(OpsDayReport(session_id=s.id, day=r["day"], policy=r["policy"], need_met=r["need_met"],
                                  worst_need_met=r["worst_need_met"], gini=r["gini"],
                                  ops_success_rate=r["ops"]["success_rate"], report=r, closed_at=now))
        db.commit()
        s.saved_seq = s.seq
        s.saved_days = list(s.day_reports)
        # operations of closed days no longer change
        s.saved_ops_from = next((i for i, o in enumerate(s.operations) if o["day"] == s.day), len(s.operations))
    except Exception as e:                         # logging must never break the operator's session
        db.rollback()
        print("ops log not saved:", e)


def _ops_call(s, db, f):
    try:
        out = f()
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\""))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    _ops_save(db, s)
    return {"result": out, "state": s.state()}


@app.post("/ops", summary="Start an operations-desk session (the week run by hand, day by day)")
def ops_start(req: OpsStart, db: DBSession = Depends(get_db)):
    if req.policy not in ops.POLICIES:
        raise HTTPException(422, f"policy must be one of {list(ops.POLICIES)}")
    s = ops.OpsSession(req.policy)
    ops.OPS[s.id] = s
    while len(ops.OPS) > 20:
        ops.OPS.pop(next(iter(ops.OPS)))
    _ops_save(db, s)
    return {"state": s.state()}


@app.get("/ops/history", summary="Closed days from every operations session, from the database")
def ops_history(limit: int = Query(50, ge=1, le=500), db: DBSession = Depends(get_db)):
    return q(db, """SELECT session_id, day, policy, need_met, worst_need_met, gini, ops_success_rate, closed_at
                    FROM ops_day_reports ORDER BY closed_at DESC, day DESC LIMIT :n""", n=limit)


@app.get("/ops/{session_id}", summary="Operations-desk state")
def ops_state(session_id: str):
    return {"state": _ops(session_id).state()}


@app.get("/ops/{session_id}/supply", summary="Today's supply options, with every centre's stock under each")
def ops_supply_options(session_id: str):
    return _ops(session_id).supply_options()


@app.post("/ops/{session_id}/supply", summary="Choose today's supply (before the first wave)")
def ops_supply(session_id: str, req: OpsSupply, db: DBSession = Depends(get_db)):
    s = _ops(session_id)
    return _ops_call(s, db, lambda: s.set_supply(req.option, req.overrides))


@app.get("/ops/{session_id}/dataset", summary="Today's crisis reports from the dataset that can be added")
def ops_dataset(session_id: str, district: Optional[str] = None, search: Optional[str] = None):
    s = _ops(session_id)
    rows = ops.reports_for(s.day)
    if district:
        rows = [x for x in rows if x["district"] == district]
    if search:
        rows = [x for x in rows if search.lower() in x["text"].lower()]
    return [x | {"added": x["tweet_id"] in s.used_reports} for x in rows]


@app.post("/ops/{session_id}/report", summary="Add a dataset report (tweet_id) or a typed report; the next wave is re-planned")
def ops_report(session_id: str, req: OpsReport, db: DBSession = Depends(get_db)):
    s = _ops(session_id)
    if not req.tweet_id and not req.text:
        raise HTTPException(422, "give a tweet_id or a text")
    if req.district and req.district not in s.env.districts:
        raise HTTPException(422, f"unknown district {req.district}")
    return _ops_call(s, db, lambda: s.add_report(req.tweet_id, req.text, req.district))


@app.post("/ops/{session_id}/dispatch", summary="Send the next wave: one operation per centre-to-district trip")
def ops_dispatch(session_id: str, db: DBSession = Depends(get_db)):
    s = _ops(session_id)
    return _ops_call(s, db, s.dispatch)


@app.post("/ops/{session_id}/operations/{op_id}", summary="A rescue team's report for one operation: success or fail")
def ops_outcome(session_id: str, op_id: str, req: OpsOutcome, db: DBSession = Depends(get_db)):
    s = _ops(session_id)
    return _ops_call(s, db, lambda: s.outcome(op_id, req.status, req.reason, req.note))


@app.post("/ops/{session_id}/simulate_outcomes",
          summary="Fill in the missing team reports: at random (likelier to fail on slowed roads), or all successful")
def ops_simulate(session_id: str, all_success: bool = False, db: DBSession = Depends(get_db)):
    s = _ops(session_id)
    return _ops_call(s, db, lambda: s.simulate_outcomes(all_success))


@app.post("/ops/{session_id}/close_day", summary="Close the day and get its report; force=true counts missing reports as failed")
def ops_close(session_id: str, force: bool = False, db: DBSession = Depends(get_db)):
    s = _ops(session_id)
    return _ops_call(s, db, lambda: s.close_day(force))


@app.get("/ops/{session_id}/log.csv", summary="The session's operations log as CSV (from the database)")
def ops_log_csv(session_id: str, db: DBSession = Depends(get_db)):
    import csv as _csv
    import io
    from fastapi.responses import Response
    rows = q(db, """SELECT day, op_id, wave, district, centres, items, hours, status, reason, note, reported_at
                    FROM ops_operations WHERE session_id = :s ORDER BY day, op_id""", s=session_id)
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["day", "operation", "wave", "district", "centres", "food_kits", "water_litres", "medicine_kits",
                "rescue_teams", "hours", "status", "reason", "note", "reported_at"])
    for r in rows:
        it = r["items"] or {}
        w.writerow([r["day"], r["op_id"], r["wave"], r["district"], " ".join(r["centres"] or [])] +
                   [it.get(k, 0) for k in ("food_kits", "water_litres", "medicine_kits", "rescue_teams")] +
                   [r["hours"], r["status"], r["reason"] or "", r["note"] or "", r["reported_at"] or ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=operations-{session_id}.csv"})
