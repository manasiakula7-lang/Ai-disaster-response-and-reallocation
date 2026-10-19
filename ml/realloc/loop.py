"""Step 6: dynamic reallocation loop.

The flood week is replayed hour by hour. Two kinds of events arrive:

  reports  the real HumAID tweets from 18-24 Aug 2018 that Step 1 marked
           actionable and placed in a district (449 of them), at their real
           posting time (IST). A report about district D and resource R moves
           the planner's estimate of D's need for R halfway to the true value.
  roads    the simulator's road closures, slowdowns and reopenings
           (data/simulated/road_events.csv), each given a random time of day.

Trucks leave in 4 dispatch waves a day (06:00, 12:00, 18:00, 24:00), each
with a quarter of every centre's daily truck trips. Before each wave the loop:

  1. applies every event that arrived since the last wave
     (demand estimate, open/closed roads, travel times)
  2. re-runs the allocation policy on the remaining need, remaining stock and
     roads as now known
  3. sends that wave and writes alerts (big jump in reported need, a district
     cut off, a badly hit district still under 25% covered at day end)

Three information modes:
  static   plans every wave with what was known at 00:00: a morning forecast
           of demand (+-35% error) and yesterday's road map
  dynamic  the loop above
  roads / reports   the loop, but reacting to only one kind of event
  perfect  knows true demand and today's roads from 00:00 (upper reference)

Two policies plug into the loop:
  MAPPO    the Step 4 fair agents (ml/marl/models/ppo_fair.pt)
  LP       the fairness LP with the rationing rule (ml/marl/references.py)

Simplification: the simulator's roads are a day-level state, so a closure at
15:00 also blocks a shipment planned at 06:00. Shipments on a road that turns
out to be blocked are not delivered; the stock stays at the centre.

Usage: python -m ml.realloc.loop
Outputs: ml/realloc/results/realloc_report.md, realloc_metrics.csv,
         event_log.csv and plans.csv (official week, MAPPO, dynamic)
"""
import csv
import html
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta

import networkx as nx
import numpy as np
import torch

from ml.baselines.policies import LocalFirst, LPFair
from ml.env.metrics import episode_metrics
from ml.env.relief_env import CONSUMABLES, LOCAL_TRAVEL_HR, PROC, RESOURCES, ROOT, \
    SEVERITY_START_DAY, TRUCKLOAD
from ml.marl.mappo import Actor, act
from ml.marl.multi_agent import MultiAgentRelief
from ml.marl.scenarios import ScenarioEnv
from ml.marl.train import COLS, TEST_SEEDS, table

HERE = ROOT / "ml" / "realloc"
RESULTS = HERE / "results"
WAVES = [6, 12, 18, 24]
MODES = ["static", "roads", "reports", "dynamic", "perfect"]
FORECAST_SD = 0.35
REPORT_PULL = 0.5          # each report moves the estimate halfway to the truth
RESOURCE_MAP = {"food": ["food_kits"], "water": ["water_litres"], "medicine": ["medicine_kits"],
                "rescue": ["rescue_teams"], "shelter": ["food_kits", "water_litres"]}
IST = timedelta(hours=5, minutes=30)


# ------------------------------------------------------------------ events
def load_reports():
    """Actionable, located reports per scenario day: [(hour, district, resources, tweet_id, text)]."""
    start = datetime.strptime(SEVERITY_START_DAY, "%Y-%m-%d")
    out = defaultdict(list)
    with open(PROC / "crisis_reports.csv", newline="", encoding="utf8") as f:
        for r in csv.DictReader(f):
            if r["actionable"] != "1" or not r["primary_district"]:
                continue
            t = datetime.strptime(r["posted_utc"], "%Y-%m-%d %H:%M:%S") + IST
            day = (t.date() - start.date()).days + 1
            if 1 <= day <= 7:
                res = sorted({x for k in r["resources"].split("|") if k for x in RESOURCE_MAP.get(k, [])})
                out[day].append((t.hour + t.minute / 60, r["primary_district"], res or list(RESOURCES),
                                 r["tweet_id"], html.unescape(r["text"])[:140]))
    return {d: sorted(v) for d, v in out.items()}


def road_times(env, seed=7):
    rng = random.Random(seed)
    return {(int(e["day"]), int(e["edge_id"])): round(rng.uniform(0, 24), 2)
            for day in env.events.values() for e in day}


def apply_road_event(env, state, e):
    eid = int(e["edge_id"])
    if e["status"] == "blocked":
        state[eid] = ("blocked", None)
    elif e["status"] == "slowed":
        state[eid] = ("open", float(e["travel_time_hr"]))
    else:
        base = next(x for x in env.edges if int(x["edge_id"]) == eid)
        state[eid] = ("open", float(base["travel_time_hr"]))


def travel_from(env, state):
    """Same routing as ReliefEnv._apply_events, for a given road state."""
    G = nx.Graph(); G.add_nodes_from(env.districts)
    for e in env.edges:
        s, tt = state[int(e["edge_id"])]
        if s == "open":
            G.add_edge(e["source"], e["target"], weight=tt)
    lengths = dict(nx.all_pairs_dijkstra_path_length(G, weight="weight"))
    travel = {}
    for c in env.centres:
        for d in env.districts:
            if d == c["district"]:
                travel[(c["centre_id"], d)] = LOCAL_TRAVEL_HR
            else:
                t = lengths.get(c["district"], {}).get(d)
                travel[(c["centre_id"], d)] = None if t is None else LOCAL_TRAVEL_HR + t
    return travel


# ---------------------------------------------------------------- policies
class LPPlanner:
    name = "LP fair + rationing"

    def budget(self, obs):
        today = {r: sum(v[r] for v in obs["demand"].values()) for r in CONSUMABLES}
        frac = {r: min(1.0, 1.2 * today[r] / max(obs["forecast_remaining"][r], 1e-9)) for r in CONSUMABLES}
        return {c: {r: s[r] * frac[r] for r in CONSUMABLES} for c, s in obs["stock"].items()}

    fallbacks = 0

    def allocate(self, obs, budget):
        clean = lambda v: v if v > 1e-3 else 0.0       # tiny leftovers upset GLOP
        o = dict(obs)
        o["stock"] = {c: {**{r: clean(budget[c][r]) for r in CONSUMABLES},
                          "rescue_teams": clean(s["rescue_teams"])} for c, s in obs["stock"].items()}
        o["demand"] = {d: {r: clean(v) for r, v in dv.items()} for d, dv in obs["demand"].items()}
        try:
            return LPFair()(o)
        except RuntimeError:               # rare numerical failure: fall back for this wave
            LPPlanner.fallbacks += 1
            return LocalFirst()(o)


class MappoPlanner:
    name = "MAPPO (fair)"

    def __init__(self, env):
        self.actor = Actor()
        self.actor.load_state_dict(torch.load(ROOT / "ml/marl/models/ppo_fair.pt"))
        self.actor.eval()
        self.ma = MultiAgentRelief(env)
        self.full_trucks = self.ma.trucks.copy()

    def _features(self, obs):
        self.ma.obs = obs
        self.ma.init_stock = np.array([[self.ma.env.initial_stock[c][r] for r in RESOURCES]
                                       for c in self.ma.centres])
        return self.ma.features()

    def budget(self, obs):
        release, *_ = act(self.actor, self._features(obs), deterministic=True)
        return {c: {r: obs["stock"][c][r] * release[i, k] for k, r in enumerate(CONSUMABLES)}
                for i, c in enumerate(self.ma.centres)}

    def allocate(self, obs, budget):
        f = self._features(obs)
        _, w, *_ = act(self.actor, f, deterministic=True)
        rel = np.array([[min(1.0, budget[c][r] / max(obs["stock"][c][r], 1e-9)) for r in CONSUMABLES]
                        for c in self.ma.centres])
        self.ma.trucks = np.array([obs["trucks"][c] for c in self.ma.centres], dtype=float)
        try:
            return self.ma.to_shipments(rel, w)
        finally:
            self.ma.trucks = self.full_trucks


# -------------------------------------------------------------------- loop
def run_week(env, planner, mode, seed=None, reports=None, log=None, plans=None):
    """Plays one week; returns episode metrics. log/plans lists are filled if given."""
    reports = reports if reports is not None else load_reports()
    rtimes = road_times(env)
    obs = env.reset(seed)
    frng = random.Random(500 + (seed if seed is not None else -1))
    known_roads = {int(e["edge_id"]): ("open", float(e["travel_time_hr"])) for e in env.edges}
    done = False
    while not done:
        day = obs["day"]
        truth = obs["demand"]
        if mode == "perfect":
            est = {d: dict(v) for d, v in truth.items()}
            roads = dict(env.edge_state)
        else:
            est = {d: {r: v[r] * math.exp(frng.gauss(0, FORECAST_SD)) for r in RESOURCES}
                   for d, v in truth.items()}
            roads = dict(known_roads)
        day_events = sorted([(rtimes[(day, int(e["edge_id"]))], "road", e) for e in env.events.get(day, [])] +
                            [(x[0], "report", x) for x in reports.get(day, [])],
                            key=lambda x: x[0])
        travel = travel_from(env, roads)
        sent = defaultdict(float)              # (district, resource) -> sent today
        teams_used = defaultdict(float)
        trucks = {c: n / len(WAVES) for c, n in obs["trucks"].items()}
        stock = {c: dict(s) for c, s in obs["stock"].items()}
        start_obs = {**obs, "demand": est, "travel": travel}
        budget = planner.budget(start_obs)
        shipments = defaultdict(float)
        ev_i = 0
        for wave in WAVES:
            changed = False
            while ev_i < len(day_events) and day_events[ev_i][0] <= wave:
                hour, kind, payload = day_events[ev_i]; ev_i += 1
                if mode == "static" or (mode == "roads" and kind != "road") or \
                        (mode == "reports" and kind != "report"):
                    continue
                if kind == "road":
                    apply_road_event(env, roads, payload); changed = True
                    if log is not None:
                        log.append(_row(day, hour, f"road_{payload['status']}", "",
                                        f"{payload['source']} - {payload['target']}"))
                else:
                    _, d, res, tid, text = payload
                    for r in res:
                        old = est[d][r]
                        est[d][r] += REPORT_PULL * (truth[d][r] - est[d][r])
                        if log is not None and old > 0 and abs(est[d][r] - old) / old >= 0.3:
                            log.append(_row(day, hour, "alert", d,
                                            f"need estimate for {r} changed {old:.0f} -> {est[d][r]:.0f}"))
                    if log is not None:
                        log.append(_row(day, hour, "report", d, f"{'/'.join(res)}: {text}", tid))
            if changed:
                travel = travel_from(env, roads)
                if log is not None:
                    for d in env.districts:
                        if all(travel[(c, d)] is None for c in stock):
                            log.append(_row(day, wave, "alert", d, "cut off: no open road from any centre"))
            remaining = {d: {r: max(0.0, est[d][r] - sent[d, r]) for r in RESOURCES} for d in est}
            w_obs = {**obs, "demand": remaining, "travel": travel, "trucks": trucks,
                     "stock": {c: {**{r: stock[c][r] for r in CONSUMABLES},
                                   "rescue_teams": stock[c]["rescue_teams"] - teams_used[c]} for c in stock}}
            plan = planner.allocate(w_obs, budget)
            loads = defaultdict(float)
            for (c, d, r), amt in plan.items():
                if travel.get((c, d)) is None or amt <= 0:
                    continue
                if r == "rescue_teams":
                    amt = min(amt, stock[c][r] - teams_used[c]); teams_used[c] += amt
                else:
                    amt = min(amt, budget[c][r], stock[c][r])
                    budget[c][r] -= amt; stock[c][r] -= amt
                    loads[d] += amt / TRUCKLOAD[r]
                sent[d, r] += amt
                shipments[(c, d, r)] += amt
                if plans is not None and amt > 1e-6:
                    plans.append({"day": day, "wave": f"{wave:02d}:00", "centre": c, "district": d,
                                  "resource": r, "amount": round(amt, 2)})
            if log is not None:
                top = sorted(loads.items(), key=lambda kv: -kv[1])[:3]
                log.append(_row(day, wave, "dispatch", "",
                                f"{sum(loads.values()):.0f} truckloads to {len(loads)} districts; most to " +
                                ", ".join(f"{d} ({v:.0f})" for d, v in top)))
        if mode != "perfect":
            for _, kind, payload in day_events:     # tomorrow starts from today's full road picture
                if kind == "road":
                    apply_road_event(env, known_roads, payload)
        obs, _, done, rec = env.step(dict(shipments))
        if log is not None:
            for d in env.districts:
                rows = [x for x in rec["rows"] if x["district"] == d and x["demand"] > 0]
                cov = np.mean([x["covered"] / x["demand"] for x in rows]) if rows else 1.0
                if env.severity.get(rec["day"], {}).get(d, 0) >= 0.3 and cov < 0.25:
                    log.append(_row(rec["day"], 24, "alert", d, f"neglected: only {cov:.0%} of need met today"))
    return episode_metrics(env)


def _row(day, hour, kind, district, detail, tweet_id=""):
    h = int(hour); m = int(round((hour - h) * 60))
    return {"day": day, "time": f"{h:02d}:{m % 60:02d}", "type": kind, "district": district,
            "detail": detail, "tweet_id": tweet_id}


def main():
    env = ScenarioEnv()
    reports = load_reports()
    planners = [MappoPlanner(env), LPPlanner()]
    official, test = {}, {}
    for p in planners:
        for mode in MODES:
            name = f"{p.name}, {mode}"
            official[name] = run_week(env, p, mode, None, reports)
            runs = [run_week(env, p, mode, s, reports) for s in TEST_SEEDS]
            test[name] = {k: float(np.mean([r[k] for r in runs])) for k, _, _ in COLS}
            print(f"{name:<32} official {official[name]['fulfilment']:.3f} / worst "
                  f"{official[name]['worst_district_fulfilment']:.3f}   test {test[name]['fulfilment']:.3f}"
                  f" / worst {test[name]['worst_district_fulfilment']:.3f}", flush=True)

    print(f"LP fell back to local-first in {LPPlanner.fallbacks} waves")
    RESULTS.mkdir(parents=True, exist_ok=True)
    log, plans = [], []
    run_week(env, planners[0], "dynamic", None, reports, log, plans)
    for path, rows in (("event_log.csv", log), ("plans.csv", plans)):
        with open(RESULTS / path, "w", newline="", encoding="utf8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    keys = [k for k in next(iter(official.values())) if k != "per_district"]
    with open(RESULTS / "realloc_metrics.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["policy", "evaluation"] + keys)
        for n in official:
            w.writerow([n, "official"] + [round(official[n][k], 4) for k in keys])
            w.writerow([n, f"mean of {len(TEST_SEEDS)} weeks"] + [round(test[n].get(k, float("nan")), 4)
                                                                   for k in keys])
    counts = defaultdict(int)
    for r in log:
        counts[r["type"]] += 1
    (RESULTS / "realloc_report.md").write_text(
        "# Step 6: dynamic reallocation loop\n\n## Official scenario\n\n" + table(official) +
        f"\n\n## Average over {len(TEST_SEEDS)} unseen flood weeks\n\n" + table(test) +
        "\n\n## Event log (official week, MAPPO, dynamic)\n\n" +
        "\n".join(f"- {k}: {v}" for k, v in sorted(counts.items())) + "\n")


if __name__ == "__main__":
    main()
