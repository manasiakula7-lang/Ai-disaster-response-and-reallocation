"""Randomised versions of the 7-day Kerala scenario, for training and testing RL.

Training on one fixed week would let the agents memorise it. ScenarioEnv keeps
the same districts, centres and roads but, for each seed, redraws:

  flood curve   peak on day 2, 3 or 4, peak height 0.8-1.2, faster or slower
                recession (demand on each day is rescaled to the new curve)
  demand noise  +-15% per district per day (log-normal)
  stock         total stock 60-80% of the week's demand, +-10% per centre

seed=None gives the official scenario from data/simulated, unchanged.

Every policy also sees obs["forecast_remaining"]: total demand per resource
from today to the end of the week, with +-15% error. This is the only
look-ahead anyone gets (RL agents and the rationing baseline alike).
Road closures are not redrawn (they come from data/simulated/road_events.csv).
"""
import math
import random

from ml.env.relief_env import CONSUMABLES, RESOURCES, ReliefEnv

BASE_CURVE = [0.3, 0.7, 1.0, 0.9, 0.6, 0.4, 0.25]   # scenario_config.json
FORECAST_ERROR_SD = 0.15   # stands in for the Step 2 forecast being imperfect


def random_curve(rng, days=7):
    peak = rng.choice([1, 2, 3])                 # 0-based: day 2, 3 or 4
    height = rng.uniform(0.8, 1.2)
    rise, fall = rng.uniform(0.35, 0.6), rng.uniform(0.6, 0.85)
    curve = []
    for t in range(days):
        v = height * (rise ** (peak - t) if t < peak else fall ** (t - peak))
        curve.append(max(v, 0.15))
    return curve


class ScenarioEnv(ReliefEnv):
    def __init__(self):
        super().__init__()
        self.base_demand = {t: {d: dict(v) for d, v in dd.items()} for t, dd in self.demand.items()}
        self.base_stock = {c["centre_id"]: {r: float(c[r]) for r in RESOURCES} for c in self.centres}
        self.seed = None

    def reset(self, seed=None):
        self.seed = seed
        frng = random.Random(10_000 + (seed if seed is not None else -1))
        self.forecast_noise = {t: {r: math.exp(frng.gauss(0, FORECAST_ERROR_SD)) for r in RESOURCES}
                               for t in self.days}
        if seed is None:
            self.demand = {t: {d: dict(v) for d, v in dd.items()} for t, dd in self.base_demand.items()}
            obs = super().reset()
            self.initial_stock = {c: dict(s) for c, s in self.stock.items()}
            return obs
        rng = random.Random(seed)
        curve = random_curve(rng, len(self.days))
        self.demand = {}
        for i, t in enumerate(self.days):
            scale = curve[i] / BASE_CURVE[i]
            self.demand[t] = {}
            for d, v in self.base_demand[t].items():
                noise = math.exp(rng.gauss(0, 0.15))
                row = {r: v[r] * scale * noise for r in CONSUMABLES}
                row["rescue_teams"] = float(round(v["rescue_teams"] * scale * noise))
                self.demand[t][d] = row
        ratio = rng.uniform(0.6, 0.8)
        week = {r: sum(self.demand[t][d][r] for t in self.days for d in self.districts) for r in CONSUMABLES}
        base_week = {r: sum(s[r] for s in self.base_stock.values()) for r in CONSUMABLES}
        obs = super().reset()
        for c, s in self.base_stock.items():
            jitter = rng.uniform(0.9, 1.1)
            for r in CONSUMABLES:
                # keep each centre's share of stock, rescale the total to ratio x week demand
                self.stock[c][r] = s[r] * jitter * ratio * week[r] / base_week[r]
        self.initial_stock = {c: dict(s) for c, s in self.stock.items()}
        return self.observe()

    def observe(self):
        obs = super().observe()
        i = self.days.index(self.day)
        obs["forecast_remaining"] = {
            r: self.forecast_noise[self.day][r] * sum(self.demand[t][d][r] for t in self.days[i:]
                                                      for d in self.districts)
            for r in RESOURCES}
        obs["days_left"] = len(self.days) - i
        return obs
