"""Two non-learned reference points for judging the RL agents.

LPRationed   The Step 3 fairness LP, but each day it may only use a share of
             the stock: 1.2 x today's demand / forecast demand for the rest of the
             week (same +-15% forecast the agents see; 1.2 = margin for forecast
             error). A hand-written rule
             for the rationing the agents have to learn.
hindsight_optimum
             One LP over the whole week that knows every day's demand and road
             closure in advance. No real policy can know this, so it is an
             upper bound on fulfilment, not a competitor.
"""
from ortools.linear_solver import pywraplp

from ml.baselines.policies import LPFair
from ml.env.relief_env import CONSUMABLES, RESOURCES, TRUCKLOAD


class LPRationed(LPFair):
    name = "LP fair + rationing rule"

    def __call__(self, obs):
        today = {r: sum(v[r] for v in obs["demand"].values()) for r in CONSUMABLES}
        frac = {r: min(1.0, 1.2 * today[r] / max(obs["forecast_remaining"][r], 1e-9))
                for r in CONSUMABLES}
        limited = dict(obs)
        limited["stock"] = {c: {r: s[r] * frac.get(r, 1.0) for r in RESOURCES}
                            for c, s in obs["stock"].items()}
        return super().__call__(limited)


def hindsight_optimum(env, seed=None):
    """Plays the week with a plan made knowing everything; returns env (log filled)."""
    # roads do not depend on actions, so record each day's travel times first
    obs, travel, demand, days = env.reset(seed), {}, {}, []
    done = False
    while not done:
        days.append(obs["day"]); travel[obs["day"]] = obs["travel"]; demand[obs["day"]] = obs["demand"]
        obs, _, done, _ = env.step({})
    start = env.reset(seed)
    unit = {r: TRUCKLOAD.get(r, 1.0) for r in RESOURCES}
    trucks = start["trucks"]
    centres, districts = list(start["stock"]), env.districts
    s = pywraplp.Solver.CreateSolver("GLOP")
    x, cov = {}, {}
    for t in days:
        for (c, d), tt in travel[t].items():
            if tt is not None:
                for r in RESOURCES:
                    x[t, c, d, r] = s.NumVar(0, s.infinity(), "")
        for d in districts:
            for r in RESOURCES:
                dem = demand[t][d][r] / unit[r]
                cov[t, d, r] = s.NumVar(0, dem, "")
                s.Add(cov[t, d, r] <= sum(x[t, c, d, r] for c in centres if (t, c, d, r) in x))
        for c in centres:
            s.Add(sum(x[t, c, d, r] for d in districts for r in CONSUMABLES if (t, c, d, r) in x)
                  <= trucks[c])
            s.Add(sum(x[t, c, d, "rescue_teams"] for d in districts if (t, c, d, "rescue_teams") in x)
                  <= start["stock"][c]["rescue_teams"])
    for c in centres:
        for r in CONSUMABLES:
            s.Add(sum(v for (t, cc, d, rr), v in x.items() if cc == c and rr == r)
                  <= start["stock"][c][r] / unit[r])
    total = {r: sum(demand[t][d][r] for t in days for d in districts) / unit[r] or 1.0 for r in RESOURCES}
    obj = sum(v / total[r] for (t, d, r), v in cov.items())
    pen = sum(travel[t][c, d] * v for (t, c, d, r), v in x.items() if r in CONSUMABLES)
    s.Maximize(obj - 1e-5 * pen)
    if s.Solve() != pywraplp.Solver.OPTIMAL:
        raise RuntimeError("hindsight LP not solved")
    done = False
    while not done:
        t = env.day
        plan = {(c, d, r): v.solution_value() * unit[r]
                for (tt, c, d, r), v in x.items() if tt == t and v.solution_value() > 1e-7}
        _, _, done, _ = env.step(plan)
    return env
