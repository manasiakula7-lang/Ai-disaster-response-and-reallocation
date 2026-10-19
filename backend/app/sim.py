"""Simulation and what-if runs behind the API.

A simulation session holds one ReliefEnv week in memory and advances it one
day per /simulate/{id}/step call, with the chosen policy. What-if runs play a
whole week with changes (closed roads, more/less stock, more/less demand) and
compare it with the same week unchanged.
"""
import copy
import uuid
from collections import defaultdict

import numpy as np
import torch

from ml.baselines.policies import GreedySeverity, LocalFirst, LPEfficient, LPFair
from ml.env.metrics import episode_metrics
from ml.env.relief_env import CONSUMABLES, RESOURCES, ROOT
from ml.marl.mappo import Actor, act
from ml.marl.multi_agent import MultiAgentRelief
from ml.marl.references import LPRationed
from ml.marl.scenarios import ScenarioEnv

METRIC_KEYS = ["fulfilment", "vuln_weighted_fulfilment", "worst_district_fulfilment", "gini",
               "avg_delay_hr", "neglect_district_days"]


class WhatIfEnv(ScenarioEnv):
    """ScenarioEnv with roads forced closed and stock/demand scaled."""

    def __init__(self, closed_edges=(), stock_factor=1.0, demand_factor=1.0):
        super().__init__()
        self.base_events = copy.deepcopy(self.events)
        self.closed = set(int(e) for e in closed_edges)
        self.stock_factor, self.demand_factor = stock_factor, demand_factor

    def _closure_events(self, edges, days):
        for e in edges:
            src = next(x for x in self.edges if int(x["edge_id"]) == e)
            for d in days:
                self.events[d].append({"day": str(d), "edge_id": str(e), "source": src["source"],
                                       "target": src["target"], "status": "blocked", "travel_time_hr": ""})

    def reset(self, seed=None):
        self.events = copy.deepcopy(self.base_events)
        self._closure_events(self.closed, self.days)
        super().reset(seed)
        for t in self.days:
            for d in self.districts:
                for r in RESOURCES:
                    self.demand[t][d][r] *= self.demand_factor
        for c in self.stock:
            for r in CONSUMABLES:
                self.stock[c][r] *= self.stock_factor
        self.initial_stock = {c: dict(s) for c, s in self.stock.items()}
        return self.observe()

    def close_road(self, edge_id):
        """Close a road from today until the end of the week."""
        edge_id = int(edge_id)
        self.closed.add(edge_id)
        self._closure_events([edge_id], [t for t in self.days if t >= self.day])
        self._apply_events()   # re-applies today's events, now including the closure


class MappoPolicy:
    name = "MAPPO + fairness (Step 4)"

    def __init__(self, env):
        self.env = env
        self.actor = Actor()
        self.actor.load_state_dict(torch.load(ROOT / "ml/marl/models/ppo_fair.pt"))
        self.actor.eval()
        self.ma = MultiAgentRelief(env)

    def __call__(self, obs):
        self.ma.obs = obs
        self.ma.init_stock = np.array([[self.env.initial_stock[c][r] for r in RESOURCES]
                                       for c in self.ma.centres])
        release, w, *_ = act(self.actor, self.ma.features(), deterministic=True)
        return self.ma.to_shipments(release, w)


POLICIES = {
    "local_first": lambda env: LocalFirst(),
    "greedy": lambda env: GreedySeverity(),
    "lp": lambda env: LPEfficient(),
    "lp_fair": lambda env: LPFair(),
    "lp_rationed": lambda env: LPRationed(),
    "mappo": MappoPolicy,
}


def summarise(m):
    return {k: float(m[k]) for k in METRIC_KEYS} | {
        "per_district": {d: float(v) for d, v in m["per_district"].items()}}


def day_summary(rec, shipments):
    cov = defaultdict(list)
    out = {}
    for row in rec["rows"]:
        d = out.setdefault(row["district"], {})
        d[row["resource"]] = {"demand": row["demand"], "delivered": row["delivered"]}
        if row["demand"] > 0:
            cov[row["district"]].append(row["covered"] / row["demand"])
    for d in out:
        out[d]["coverage"] = float(np.mean(cov[d])) if cov[d] else 1.0
    return {"day": rec["day"], "avg_delay_hr": rec["avg_delay_hr"], "truckloads": rec["loads"],
            "rejected": rec["rejected"], "districts": out,
            "shipments": [{"centre": c, "district": d, "resource": r, "amount": a}
                          for (c, d, r), a in shipments.items()]}


class Session:
    def __init__(self, policy, seed=None, closed_edges=(), stock_factor=1.0, demand_factor=1.0):
        self.id = uuid.uuid4().hex[:8]
        self.env = WhatIfEnv(closed_edges, stock_factor, demand_factor)
        self.policy_name = policy
        self.policy = POLICIES[policy](self.env)
        self.obs = self.env.reset(seed)
        self.done = False
        self.days = []

    def step(self):
        if self.done:
            raise ValueError("week already finished")
        shipments = self.policy(self.obs)
        self.obs, _, self.done, rec = self.env.step(shipments)
        s = day_summary(rec, shipments)
        self.days.append(s)
        return s

    def state(self):
        return {"session_id": self.id, "policy": self.policy_name, "done": self.done,
                "next_day": None if self.done else self.env.day, "days_played": len(self.days),
                "closed_roads": sorted(self.env.closed),
                "stock_left": {c: dict(s) for c, s in self.env.stock.items()},
                "metrics": summarise(episode_metrics(self.env)) if self.env.log else None}


SESSIONS: dict[str, Session] = {}


def play_week(policy, seed=None, closed_edges=(), stock_factor=1.0, demand_factor=1.0):
    s = Session(policy, seed, closed_edges, stock_factor, demand_factor)
    while not s.done:
        s.step()
    return summarise(episode_metrics(s.env))


def what_if(policy, seed=None, closed_edges=(), stock_factor=1.0, demand_factor=1.0):
    base = play_week(policy, seed)
    changed = play_week(policy, seed, closed_edges, stock_factor, demand_factor)
    return {"policy": policy, "baseline": base, "what_if": changed,
            "change": {k: changed[k] - base[k] for k in METRIC_KEYS}}
