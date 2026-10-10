"""Relief allocation simulator for the Kerala 2018 flood scenario (Step 3).

Each day every relief centre decides how much of each resource to send to each
district. The environment enforces stock, truck capacity and road access,
applies the day's road closures, scores the day, and moves on.

Inputs (data/simulated, data/processed):
  relief_centres.csv          19 centres: stock, vehicles
  demand_timeline.csv         7 days x 14 districts demand
  road_edges.csv, road_events.csv   network and day-by-day closures/slowdowns
  district_severity_daily.csv GAT severity (day 1 = 18 Aug 2018)
  graph_nodes.csv             vulnerability scores

Resources: food_kits, water_litres, medicine_kits are consumed when delivered;
rescue_teams are reassigned every day (not consumed).

Policies call env.reset() then repeatedly env.step(shipments) where
shipments = {(centre_id, district, resource): amount}.
"""
import csv
from collections import defaultdict
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[2]
SIM = ROOT / "data" / "simulated"
PROC = ROOT / "data" / "processed"

CONSUMABLES = ["food_kits", "water_litres", "medicine_kits"]
RESOURCES = CONSUMABLES + ["rescue_teams"]
TRUCKLOAD = {"food_kits": 1000, "water_litres": 25000, "medicine_kits": 500}
TRIPS_PER_VEHICLE = 2
LOCAL_TRAVEL_HR = 1.0           # delivery inside the centre's own district
SEVERITY_START_DAY = "2018-08-18"  # scenario day 1


def _read(path):
    with open(path, newline="", encoding="utf8") as f:
        return list(csv.DictReader(f))


class ReliefEnv:
    def __init__(self):
        self.centres = _read(SIM / "relief_centres.csv")
        self.districts = [r["district"] for r in sorted(_read(PROC / "graph_nodes.csv"),
                                                          key=lambda r: int(r["node_id"]))]
        self.vulnerability = {r["district"]: float(r["vulnerability_score"])
                              for r in _read(PROC / "graph_nodes.csv")}
        self.demand = defaultdict(dict)  # day -> district -> resource -> amount
        for r in _read(SIM / "demand_timeline.csv"):
            self.demand[int(r["day"])][r["district"]] = {k: float(r[k]) for k in RESOURCES}
        self.days = sorted(self.demand)
        self.edges = _read(SIM / "road_edges.csv")
        self.events = defaultdict(list)
        for e in _read(SIM / "road_events.csv"):
            self.events[int(e["day"])].append(e)
        sev = _read(PROC / "district_severity_daily.csv")
        dates = sorted({r["date"] for r in sev})
        start = dates.index(SEVERITY_START_DAY)
        self.severity = defaultdict(dict)
        for r in sev:
            d = dates.index(r["date"]) - start + 1
            if 1 <= d <= len(self.days):
                self.severity[d][r["district"]] = float(r["severity"])

    # ------------------------------------------------------------------ state
    def reset(self):
        self.day = self.days[0]
        self.stock = {c["centre_id"]: {r: float(c[r]) for r in RESOURCES} for c in self.centres}
        self.edge_state = {int(e["edge_id"]): ("open", float(e["travel_time_hr"])) for e in self.edges}
        self.log = []
        self._apply_events()
        return self.observe()

    def _apply_events(self):
        for e in self.events.get(self.day, []):
            base = float(next(x["travel_time_hr"] for x in self.edges if x["edge_id"] == e["edge_id"]))
            if e["status"] == "blocked":
                self.edge_state[int(e["edge_id"])] = ("blocked", None)
            elif e["status"] == "slowed":
                self.edge_state[int(e["edge_id"])] = ("open", float(e["travel_time_hr"]))
            else:
                self.edge_state[int(e["edge_id"])] = ("open", base)
        G = nx.Graph()
        G.add_nodes_from(self.districts)
        for e in self.edges:
            status, tt = self.edge_state[int(e["edge_id"])]
            if status == "open":
                G.add_edge(e["source"], e["target"], weight=tt)
        self.graph = G
        lengths = dict(nx.all_pairs_dijkstra_path_length(G, weight="weight"))
        self.travel = {}
        for c in self.centres:
            for d in self.districts:
                if d == c["district"]:
                    self.travel[(c["centre_id"], d)] = LOCAL_TRAVEL_HR
                else:
                    t = lengths.get(c["district"], {}).get(d)
                    self.travel[(c["centre_id"], d)] = None if t is None else LOCAL_TRAVEL_HR + t

    def observe(self):
        return {
            "day": self.day,
            "demand": self.demand[self.day],
            "severity": self.severity.get(self.day, {}),
            "vulnerability": self.vulnerability,
            "stock": {c: dict(s) for c, s in self.stock.items()},
            "trucks": {c["centre_id"]: int(c["vehicles"]) * TRIPS_PER_VEHICLE for c in self.centres},
            "travel": dict(self.travel),  # None = unreachable today
            "centre_district": {c["centre_id"]: c["district"] for c in self.centres},
            "blocked_edges": [e for e, (s, _) in self.edge_state.items() if s == "blocked"],
        }

    # ------------------------------------------------------------------- step
    def step(self, shipments):
        obs = self.observe()
        delivered = defaultdict(lambda: defaultdict(float))
        trucks_used = defaultdict(float)
        teams_used = defaultdict(float)
        time_weighted, loads = 0.0, 0.0
        rejected = 0.0
        for (c, d, r), amt in sorted(shipments.items(), key=lambda kv: self.travel.get(kv[0][:2]) or 1e9):
            if amt <= 0:
                continue
            t = self.travel.get((c, d))
            if t is None:
                rejected += amt
                continue
            if r == "rescue_teams":
                amt = min(amt, self.stock[c][r] - teams_used[c])
                teams_used[c] += amt
            else:
                amt = min(amt, self.stock[c][r])
                free = obs["trucks"][c] - trucks_used[c]
                amt = min(amt, free * TRUCKLOAD[r])
                trucks_used[c] += amt / TRUCKLOAD[r]
                self.stock[c][r] -= amt
                time_weighted += t * amt / TRUCKLOAD[r]
                loads += amt / TRUCKLOAD[r]
            if amt > 0:
                delivered[d][r] += amt

        record = {"day": self.day, "rows": []}
        for d in self.districts:
            for r in RESOURCES:
                dem = self.demand[self.day][d][r]
                got = delivered[d][r]
                record["rows"].append({"district": d, "resource": r, "demand": dem,
                                       "delivered": got, "covered": min(dem, got)})
        record["avg_delay_hr"] = time_weighted / loads if loads else 0.0
        record["loads"] = loads
        record["rejected"] = rejected
        self.log.append(record)

        reward = self._day_score(record)
        i = self.days.index(self.day)
        done = i == len(self.days) - 1
        if not done:
            self.day = self.days[i + 1]
            self._apply_events()
        return self.observe(), reward, done, record

    @staticmethod
    def _day_score(record):
        """Mean coverage ratio over resources with demand (0-1)."""
        tot = defaultdict(lambda: [0.0, 0.0])
        for row in record["rows"]:
            tot[row["resource"]][0] += row["covered"]
            tot[row["resource"]][1] += row["demand"]
        ratios = [c / d for c, d in tot.values() if d > 0]
        return sum(ratios) / len(ratios) if ratios else 1.0
