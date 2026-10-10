"""Daily district-graph snapshots for the Kerala 2018 floods.

One PyG graph per day (17 Aug - 12 Sep 2018, from tweet times). Nodes are the
14 districts, edges are the Phase 1 adjacency edges (both directions) with
travel time as the edge feature.

Node features (19):
  static (9):  log population, rural share, vulnerability score,
               flood exposure for the 6 return periods
  dynamic (10): from the NLP signals: log1p of reports, actionable reports,
               urgency sum and the 5 resource needs on day t, plus the
               2-day trailing mean of urgency and the statewide urgency on day t
Target: log1p(urgency-weighted demand) of each district on day t+1.
"""
import csv
import math
from datetime import date, timedelta
from pathlib import Path

import torch
from torch_geometric.data import Data

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
SIMULATED = ROOT / "data" / "simulated"
FLOOD_COLS = [f"flood_exposure_{p}yr" for p in (10, 25, 50, 100, 200, 500)]
NEEDS = ["need_food", "need_water", "need_medicine", "need_rescue", "need_shelter"]
START, END = date(2018, 8, 17), date(2018, 9, 12)


def _read(path):
    with open(path, newline="", encoding="utf8") as f:
        return list(csv.DictReader(f))


def load_static():
    nodes = sorted(_read(PROCESSED / "graph_nodes.csv"), key=lambda r: int(r["node_id"]))
    names = [n["district"] for n in nodes]
    feats = []
    for n in nodes:
        pop = float(n["population_2018"])
        feats.append([math.log(pop), float(n["rural_population_2018"]) / pop,
                      float(n["vulnerability_score"])] + [float(n[c]) for c in FLOOD_COLS])
    x = torch.tensor(feats, dtype=torch.float)
    x = (x - x.mean(0)) / (x.std(0) + 1e-6)

    edges = _read(SIMULATED / "road_edges.csv")
    src = [int(e["source_id"]) for e in edges] + [int(e["target_id"]) for e in edges]
    dst = [int(e["target_id"]) for e in edges] + [int(e["source_id"]) for e in edges]
    tt = [float(e["travel_time_hr"]) for e in edges] * 2
    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_attr = torch.tensor(tt, dtype=torch.float).unsqueeze(1)
    edge_attr = edge_attr / edge_attr.max()
    return names, x, nodes, edge_index, edge_attr


def load_signals(names):
    days = [START + timedelta(d) for d in range((END - START).days + 1)]
    idx = {n: i for i, n in enumerate(names)}
    cols = ["reports", "actionable_reports", "urgency_sum"] + NEEDS
    sig = torch.zeros(len(days), len(names), len(cols))
    day_idx = {d.isoformat(): i for i, d in enumerate(days)}
    for r in _read(PROCESSED / "district_daily_signals.csv"):
        if r["date"] in day_idx:
            sig[day_idx[r["date"]], idx[r["district"]]] = torch.tensor([float(r[c]) for c in cols])
    return days, torch.log1p(sig)


def build_snapshots():
    """Returns (names, days, list of Data). Snapshot k uses day k, target day k+1."""
    names, x_static, nodes, edge_index, edge_attr = load_static()
    days, sig = load_signals(names)
    urg = sig[:, :, 2]
    snaps = []
    for t in range(len(days) - 1):
        trailing = urg[max(0, t - 2):t].mean(0) if t > 0 else torch.zeros(len(names))
        statewide = torch.full((len(names),), float(urg[t].sum()) / len(names))
        x_dyn = torch.cat([sig[t], trailing.unsqueeze(1), statewide.unsqueeze(1)], dim=1)
        snaps.append(Data(x=torch.cat([x_static, x_dyn], dim=1), edge_index=edge_index,
                          edge_attr=edge_attr, y=urg[t + 1], persistence=urg[t],
                          day=days[t].isoformat(), target_day=days[t + 1].isoformat()))
    return names, days, snaps
