"""API tests. Need the database running and loaded (python -m backend.app.load).

Run from the repo root:  python -m pytest backend/tests -q
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["postgis"]


def test_districts_geojson():
    fc = client.get("/districts", params={"day": 3}).json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 14
    props = fc["features"][0]["properties"]
    assert props["severity"] is not None and props["food_kits"] > 0
    assert fc["features"][0]["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_locate_kochi_in_ernakulam():
    assert client.get("/districts/locate", params={"lat": 9.98, "lon": 76.28}).json()["name"] == "Ernakulam"
    assert client.get("/districts/locate", params={"lat": 20.0, "lon": 70.0}).status_code == 404


def test_nearest_centres():
    rows = client.get("/centres/nearest", params={"lat": 9.98, "lon": 76.28, "k": 3}).json()
    assert len(rows) == 3 and rows[0]["district"] == "Ernakulam"
    assert rows[0]["distance_km"] <= rows[1]["distance_km"] <= rows[2]["distance_km"]


def test_centres_and_roads():
    assert len(client.get("/centres").json()["features"]) == 19
    roads = client.get("/roads", params={"day": 3}).json()["features"]
    assert len(roads) == 21
    assert {f["properties"]["status"] for f in roads} >= {"open", "blocked"}


@pytest.mark.parametrize("path,params,n", [
    ("/demand", {"day": 1}, 14), ("/severity", {"day": 1}, 14), ("/demand", {}, 98),
])
def test_tables(path, params, n):
    assert len(client.get(path, params=params).json()) == n


def test_reports_events_allocations_metrics():
    rep = client.get("/reports", params={"district": "Alappuzha", "actionable": True, "limit": 5}).json()
    assert 0 < len(rep) <= 5 and all(r["district"] == "Alappuzha" and r["actionable"] == 1 for r in rep)
    assert len(client.get("/events", params={"type": "report"}).json()) == 449
    assert all(e["type"] == "alert" for e in client.get("/alerts").json())
    by_d = client.get("/allocations", params={"day": 1, "group_by": "district"}).json()
    assert by_d and {"district", "resource", "amount"} <= set(by_d[0])
    m = client.get("/metrics", params={"step": "3"}).json()
    assert len(m) == 4 and abs(m[2]["fulfilment"] - 0.678) < 0.001


def test_simulation_session():
    s = client.post("/simulate", json={"policy": "lp_fair"}).json()
    sid = s["session_id"]
    day1 = client.post(f"/simulate/{sid}/step").json()
    assert day1["day"] == 1 and len(day1["districts"]) == 14
    closed = client.post(f"/simulate/{sid}/close_road", json={"edge_id": 0}).json()
    assert 0 in closed["closed_roads"]
    for _ in range(6):
        last = client.post(f"/simulate/{sid}/step").json()
    assert last["state"]["done"] and 0 < last["state"]["metrics"]["fulfilment"] < 1
    assert client.post(f"/simulate/{sid}/step").status_code == 409
    saved = client.get("/allocations", params={"run_id": sid, "day": 2}).json()
    assert saved and all(a["day"] == 2 for a in saved)


def test_simulation_matches_step3():
    """The API session gives the same result as the Step 3 evaluation."""
    sid = client.post("/simulate", json={"policy": "lp"}).json()["session_id"]
    for _ in range(7):
        r = client.post(f"/simulate/{sid}/step").json()
    assert abs(r["state"]["metrics"]["fulfilment"] - 0.678) < 0.001


def test_whatif_less_stock_hurts():
    r = client.post("/whatif", json={"policy": "mappo", "stock_factor": 0.5}).json()
    assert r["change"]["fulfilment"] < -0.1
    assert client.post("/whatif", json={"policy": "nope"}).status_code == 422
