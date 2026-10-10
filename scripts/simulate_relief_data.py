"""Generate simulated relief-centre, demand and road-status data for the
Kerala 2018 flood scenario.

Real relief-centre operations data isn't available, so this builds a
plausible, reproducible stand-in from the Phase 1 processed data
(population, vulnerability, flood exposure, district adjacency).

Outputs (data/simulated/):
  district_locations.csv  approximate district HQ coordinates
  road_edges.csv          graph edges with road distance and travel time
  relief_centres.csv      centres with capacity and starting stock
  demand_timeline.csv     daily demand per district and resource
  road_events.csv         road closures/reopenings over the scenario
  scenario_config.json    every assumption used, for the write-up

Usage: python scripts/simulate_relief_data.py [--seed 42] [--days 7]
"""
import argparse
import csv
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "data" / "simulated"

# District headquarters (lat, lon) from data/raw/boundaries/KERALA_DISTRICT_HQ.dbf.
DISTRICT_HQ = {
    "Alappuzha": (9.4969, 76.3272),
    "Ernakulam": (10.0198, 76.3444),
    "Idukki": (9.8571, 76.9475),
    "Kannur": (11.8710, 75.3759),
    "Kasaragod": (12.5052, 74.9889),
    "Kollam": (8.8898, 76.5756),
    "Kottayam": (9.5890, 76.5264),
    "Kozhikode": (11.2452, 75.7837),
    "Malappuram": (11.0483, 76.0749),
    "Palakkad": (10.7777, 76.6556),
    "Pathanamthitta": (9.2640, 76.7884),
    "Thiruvananthapuram": (8.4906, 76.9484),
    "Thrissur": (10.5166, 76.2124),
    "Wayanad": (11.6131, 76.0818),
}

RESOURCES = ["food_kits", "water_litres", "medicine_kits", "rescue_teams"]

CONFIG = {
    # Day-by-day flood intensity, shaped like the Aug 2018 peak (days 3-4).
    "severity_curve": [0.3, 0.7, 1.0, 0.9, 0.6, 0.4, 0.25],
    # Return period whose exposure stands in for the 2018 event.
    "exposure_column": "flood_exposure_100yr",
    # Share of people in flooded area who are displaced at peak; scaled by (1 + vulnerability).
    "displacement_rate": 0.15,
    # Per displaced person per day (Sphere-style minimums, simplified).
    "per_person_per_day": {
        "food_kits": 0.25,      # one kit per household of 4
        "water_litres": 15.0,
        "medicine_kits": 0.02,  # one kit per 50 people
    },
    "people_per_rescue_team": 20000,
    "demand_noise_sd": 0.10,
    # Total starting stock as a fraction of total scenario demand: scarce on purpose.
    "stock_to_demand_ratio": 0.7,
    # Stock is placed by population, not by flood risk, so allocation has real work to do.
    "stock_placement": "population",
    "road_factor": 1.35,        # road km per straight-line km
    "avg_speed_kmph": 35.0,
    "flooded_speed_factor": 0.5,
    "max_daily_closure_prob": 0.45,
    "reopen_prob": 0.35,
    "large_district_population": 3_000_000,
}


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=len(CONFIG["severity_curve"]))
    args = ap.parse_args()
    rng = random.Random(args.seed)
    OUT.mkdir(parents=True, exist_ok=True)

    nodes = read_csv(PROCESSED / "graph_nodes.csv")
    edges = read_csv(PROCESSED / "graph_edges.csv")
    by_name = {n["district"]: n for n in nodes}
    exp_col = CONFIG["exposure_column"]
    curve = CONFIG["severity_curve"]
    curve = (curve + [curve[-1]] * args.days)[: args.days]

    # District locations
    write_csv(OUT / "district_locations.csv", [
        {"node_id": n["node_id"], "district": n["district"],
         "lat": DISTRICT_HQ[n["district"]][0], "lon": DISTRICT_HQ[n["district"]][1]}
        for n in nodes
    ])

    # Road edges with distance and travel time
    road_edges = []
    for e in edges:
        km = haversine_km(DISTRICT_HQ[e["source"]], DISTRICT_HQ[e["target"]]) * CONFIG["road_factor"]
        road_edges.append({
            "edge_id": len(road_edges), "source_id": e["source_id"], "target_id": e["target_id"],
            "source": e["source"], "target": e["target"],
            "distance_km": round(km, 1),
            "travel_time_hr": round(km / CONFIG["avg_speed_kmph"], 2),
        })
    write_csv(OUT / "road_edges.csv", road_edges)

    # Demand timeline
    demand = []
    totals = {r: 0.0 for r in RESOURCES}
    for day, sev in enumerate(curve, start=1):
        for n in nodes:
            pop = float(n["population_2018"])
            vuln = float(n["vulnerability_score"])
            exposure = float(n[exp_col])
            displaced = pop * exposure * CONFIG["displacement_rate"] * (1 + vuln) * sev
            displaced *= max(0.0, rng.gauss(1.0, CONFIG["demand_noise_sd"]))
            row = {"day": day, "node_id": n["node_id"], "district": n["district"],
                   "severity": sev, "displaced_people": int(displaced)}
            for res, rate in CONFIG["per_person_per_day"].items():
                row[res] = int(round(displaced * rate))
            row["rescue_teams"] = math.ceil(displaced / CONFIG["people_per_rescue_team"]) if sev >= 0.5 else 0
            # Urgency 0-1: how hard this district is hit, weighted toward vulnerable areas.
            row["urgency"] = round(min(1.0, sev * (exposure / 0.45) * (0.5 + vuln)), 3)
            for r in RESOURCES:
                totals[r] += row[r]
            demand.append(row)
    write_csv(OUT / "demand_timeline.csv", demand)

    # Relief centres: one per district, two for large districts
    centres = []
    for n in nodes:
        k = 2 if float(n["population_2018"]) >= CONFIG["large_district_population"] else 1
        lat, lon = DISTRICT_HQ[n["district"]]
        for i in range(k):
            centres.append({
                "centre_id": f"RC{len(centres):02d}",
                "name": f"{n['district']} Relief Centre {i + 1}",
                "node_id": n["node_id"], "district": n["district"],
                "lat": round(lat + rng.uniform(-0.08, 0.08), 4),
                "lon": round(lon + rng.uniform(-0.08, 0.08), 4),
                "_pop_share": float(n["population_2018"]) / k,
            })
    pop_total = sum(c["_pop_share"] for c in centres)
    peak_teams = sum(r["rescue_teams"] for r in demand if r["severity"] == max(curve))
    for c in centres:
        share = c.pop("_pop_share") / pop_total
        # Stock covers ~70% of total scenario demand; rescue teams cover ~70% of the peak day.
        for res in RESOURCES[:3]:
            c[res] = int(totals[res] * CONFIG["stock_to_demand_ratio"] * share * rng.uniform(0.8, 1.2))
        c["rescue_teams"] = max(1, round(peak_teams * CONFIG["stock_to_demand_ratio"] * share))
        c["vehicles"] = rng.randint(4, 12)
        c["capacity_people"] = rng.choice([500, 1000, 1500, 2000, 3000])
    write_csv(OUT / "relief_centres.csv", centres)

    # Road events: closure risk follows flood exposure of the endpoints and the day's severity
    events = []
    max_exp = max(float(n[exp_col]) for n in nodes)
    closed = set()
    for day, sev in enumerate(curve, start=1):
        for e in road_edges:
            eid = e["edge_id"]
            risk = max(float(by_name[e["source"]][exp_col]), float(by_name[e["target"]][exp_col])) / max_exp
            if eid in closed:
                if sev < 0.9 and rng.random() < CONFIG["reopen_prob"]:
                    closed.discard(eid)
                    events.append({"day": day, "edge_id": eid, "source": e["source"],
                                   "target": e["target"], "status": "open",
                                   "travel_time_hr": e["travel_time_hr"]})
            elif rng.random() < CONFIG["max_daily_closure_prob"] * risk * sev:
                closed.add(eid)
                events.append({"day": day, "edge_id": eid, "source": e["source"],
                               "target": e["target"], "status": "blocked",
                               "travel_time_hr": ""})
            elif sev >= 0.7 and risk > 0.3:
                slow = round(e["travel_time_hr"] / CONFIG["flooded_speed_factor"], 2)
                events.append({"day": day, "edge_id": eid, "source": e["source"],
                               "target": e["target"], "status": "slowed",
                               "travel_time_hr": slow})
    write_csv(OUT / "road_events.csv", events)

    (OUT / "scenario_config.json").write_text(json.dumps(
        {"seed": args.seed, "days": args.days, **CONFIG,
         "district_hq": DISTRICT_HQ}, indent=2))

    print(f"centres={len(centres)} demand_rows={len(demand)} "
          f"road_edges={len(road_edges)} road_events={len(events)}")
    print("total demand:", {r: int(v) for r, v in totals.items()})
    print("total stock:", {r: sum(c[r] for c in centres) for r in RESOURCES})


if __name__ == "__main__":
    main()
