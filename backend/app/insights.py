"""Data behind the dashboard's GAT Network, Model Analytics, Decision Support and
Resource Allocation pages.

build_artifacts() is called by the loader: it reads the Step 1-6 result files once
and returns JSON blobs that are stored in the `artifacts` table. decision() and
evaluate() run per request.
"""
import csv
import heapq
import html
import re
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np

from ml.env.relief_env import RESOURCES, ROOT, SEVERITY_START_DAY

DATA = ROOT / "data"
WAVES = ["06:00", "12:00", "18:00", "24:00"]
MIN_SHIPMENT = {"food_kits": 100, "water_litres": 2500, "medicine_kits": 50, "rescue_teams": 0.1}
# NLP need keywords -> simulator resources (same mapping as the Step 6 loop)
RESOURCE_MAP = {"food": ["food_kits"], "water": ["water_litres"], "medicine": ["medicine_kits"],
                "rescue": ["rescue_teams"], "shelter": ["food_kits", "water_litres"]}


def rows(path):
    with open(path, newline="", encoding="utf8") as f:
        return list(csv.DictReader(f))


def scenario_day(date):
    d = (datetime.strptime(date, "%Y-%m-%d") - datetime.strptime(SEVERITY_START_DAY, "%Y-%m-%d")).days + 1
    return d if 1 <= d <= 7 else None


# --------------------------------------------------------------- built at load time
def _nlp():
    text = (ROOT / "ml/nlp/results/classifier_report.md").read_text()
    head = dict(re.findall(r"\| (Macro-F1|Weighted-F1|Accuracy) \| ([\d.]+) \|", text))
    classes = []
    for m in re.finditer(r"^\s*([a-z_]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)$", text, re.M):
        classes.append({"label": m[1], "precision": float(m[2]), "recall": float(m[3]),
                        "f1": float(m[4]), "support": int(m[5])})
    readme = (ROOT / "ml/nlp/README.md").read_text()
    auroc = re.search(r"Urgency score AUROC[^|]*\| ([\d.]+)", readme)
    reports = rows(DATA / "processed/crisis_reports.csv")
    week = [r for r in reports if r["actionable"] == "1" and r["primary_district"] and scenario_day(r["date"])]
    mentions = Counter(k for r in week for k in r["resources"].split("|") if k)
    return {
        "macro_f1": float(head["Macro-F1"]), "weighted_f1": float(head["Weighted-F1"]),
        "accuracy": float(head["Accuracy"]), "urgency_auroc": float(auroc[1]) if auroc else None,
        "classes": classes,
        "tweets_total": len(reports),
        "tweets_located": sum(1 for r in reports if r["primary_district"]),
        "tweets_actionable": sum(1 for r in reports if r["actionable"] == "1"),
        "week_reports": len(week),
        "categories": Counter(r["pred_label"] for r in reports).most_common(),
        "resource_mentions": mentions.most_common(),
        "by_district": Counter(r["primary_district"] for r in week).most_common(),
    }


def _gnn():
    text = (ROOT / "ml/gnn/results/gnn_report.md").read_text()
    table = [{"split": m[1], "model": m[2], "mae": m[3], "rmse": m[4]}
             for m in re.finditer(r"^\| (temporal|spatial) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$", text, re.M)]
    att = rows(ROOT / "ml/gnn/results/attention_edges.csv")[:10]
    return {"table": table, "top_attention": [{**a, "attention": float(a["attention"])} for a in att]}


def _marl():
    curves = rows(ROOT / "ml/marl/results/learning_curves.csv")
    keep = [r for i, r in enumerate(curves) if i % 10 == 0 or i == len(curves) - 1]
    return {"learning_curves": [{k: float(v) for k, v in r.items()} for r in keep]}


def _fl():
    return {"rounds": [{k: float(v) for k, v in r.items()} for r in rows(ROOT / "ml/fl/results/rounds.csv")]}


def _per_district():
    out = {}
    for path in (ROOT / "ml/marl/results/per_district.csv",):
        for r in rows(path):
            name = r.pop("policy")
            out[name] = {d: float(v) for d, v in r.items()}
    return out


def _graph():
    hq = {r["district"]: (float(r["lat"]), float(r["lon"])) for r in rows(DATA / "simulated/district_locations.csv")}
    nodes = []
    for r in rows(DATA / "processed/graph_nodes.csv"):
        pop = int(r["population_2018"])
        nodes.append({"district": r["district"], "node_id": int(r["node_id"]), "population": pop,
                      "rural_share": round(int(r["rural_population_2018"]) / pop, 3),
                      "vulnerability": float(r["vulnerability_score"]),
                      "flood_exposure_100yr": round(float(r["flood_exposure_100yr"]), 4),
                      "lat": hq[r["district"]][0], "lon": hq[r["district"]][1]})
    edges = [{"edge_id": int(e["edge_id"]), "source": e["source"], "target": e["target"],
              "distance_km": float(e["distance_km"]), "travel_time_hr": float(e["travel_time_hr"])}
             for e in rows(DATA / "simulated/road_edges.csv")]
    centres = [{"centre_id": c["centre_id"], "name": c["name"], "district": c["district"],
                "lat": float(c["lat"]), "lon": float(c["lon"])} for c in rows(DATA / "simulated/relief_centres.csv")]
    emb = defaultdict(dict)
    for r in rows(DATA / "processed/gat_embeddings.csv"):
        d = scenario_day(r["date"])
        if d:
            emb[d][r["district"]] = [float(r[f"e{k}"]) for k in range(16)]
    att = defaultdict(dict)
    for r in rows(DATA / "processed/gat_attention_daily.csv"):
        d = scenario_day(r["date"])
        if d:
            att[d][f"{r['source']}|{r['target']}"] = float(r["attention"])
    return {"nodes": nodes, "edges": edges, "centres": centres, "embeddings": emb, "attention": att}


def build_artifacts():
    return {
        "graph": _graph(),
        "analytics": {"nlp": _nlp(), "gnn": _gnn(), "marl": _marl(), "fl": _fl(),
                      "per_district": _per_district()},
    }


# ------------------------------------------------------------------- per request
def travel(edges, events_today, src):
    """Shortest travel time (h) and hop count from district src. events_today: every road change up to
    and including the day, oldest first (a later change overrides an earlier one)."""
    status = {int(e["edge_id"]): e for e in events_today}
    adj = defaultdict(list)
    for e in edges:
        ev = status.get(e["edge_id"])
        if ev and ev["status"] == "blocked":
            continue
        t = float(ev["travel_time_hr"]) if ev and ev.get("travel_time_hr") else e["travel_time_hr"]
        adj[e["source"]].append((e["target"], t))
        adj[e["target"]].append((e["source"], t))
    best = {src: (0.0, 0)}
    heap = [(0.0, 0, src)]
    while heap:
        t, h, u = heapq.heappop(heap)
        if (t, h) != best[u]:
            continue
        for v, w in adj[u]:
            if v not in best or t + w < best[v][0]:
                best[v] = (t + w, h + 1)
                heapq.heappush(heap, (t + w, h + 1, v))
    return best


def report_resources(resources):
    return sorted({x for k in resources.split("|") if k for x in RESOURCE_MAP.get(k, [])}) or list(RESOURCES)


def next_wave(time):
    return next((w for w in WAVES if w > time), WAVES[-1])


def evaluate(session_cls, policy, baseline, closed_edges=(), stock_factor=1.0, demand_factor=1.0):
    """Play the week with two strategies on the same scenario; totals per resource, per district and per day."""
    out = {}
    for name in dict.fromkeys([policy, baseline]):
        s = session_cls(name, None, closed_edges, stock_factor, demand_factor)
        days = []
        while not s.done:
            days.append(s.step())
        per_res = {r: {"demand": 0.0, "delivered": 0.0} for r in RESOURCES}
        per_dist = defaultdict(lambda: {r: {"demand": 0.0, "delivered": 0.0} for r in RESOURCES})
        daily = []
        for day in days:
            tot = {r: [0.0, 0.0] for r in RESOURCES}
            for d, res in day["districts"].items():
                for r in RESOURCES:
                    if r not in res:
                        continue
                    dem, got = res[r]["demand"], min(res[r]["demand"], res[r]["delivered"])
                    per_res[r]["demand"] += dem; per_res[r]["delivered"] += got
                    per_dist[d][r]["demand"] += dem; per_dist[d][r]["delivered"] += got
                    tot[r][0] += dem; tot[r][1] += got
            ratios = [g / dm for dm, g in tot.values() if dm > 0]
            daily.append({"day": day["day"], "met": float(np.mean(ratios)) if ratios else 1.0,
                          "worst": min(v["coverage"] for v in day["districts"].values()),
                          "truckloads": day["truckloads"]})
        from ml.env.metrics import episode_metrics
        from backend.app.sim import summarise
        out[name] = {"metrics": summarise(episode_metrics(s.env)), "per_resource": per_res,
                     "per_district": per_dist, "daily": daily}
        env = s.env
    timeline = []
    for t in env.days:
        for e in env.events.get(t, []):
            timeline.append({"day": t, "kind": "road", "status": e["status"],
                             "detail": f"{e['source']} – {e['target']}",
                             "closed_by_user": int(e["edge_id"]) in env.closed})
        if t > env.days[0]:
            for d in env.districts:
                prev = sum(env.demand[t - 1][d].values())
                now = sum(env.demand[t][d].values())
                if prev > 0 and now / prev >= 1.3:
                    timeline.append({"day": t, "kind": "demand", "district": d,
                                     "detail": f"demand in {d} up {now / prev - 1:.0%}",
                                     "change": {r: round(env.demand[t][d][r] - env.demand[t - 1][d][r], 1)
                                                for r in RESOURCES}})
    seen, dedup = set(), []
    for x in timeline:   # a closure is repeated every day; keep the first day it appears
        k = (x["kind"], x["detail"], x.get("status"))
        if k not in seen:
            seen.add(k); dedup.append(x)
    return {"policy": policy, "baseline": baseline, "results": out, "timeline": dedup,
            "vulnerability": {d: float(env.vulnerability[d]) for d in env.districts}}


def clean_text(t):
    return html.unescape(t)
