"""Multi-agent view of the relief simulator: one agent per relief centre.

Each day every centre (agent) sees
  global   day, days left, total stock vs today's demand and vs the forecast for
           the rest of the week, trucks vs truckloads needed today
  own      its stock left (vs its starting stock and vs all centres), its trucks
  per district/resource
           today's demand, GAT severity, vulnerability, travel time from this
           centre, whether the road is open, whether it is the closest centre

and chooses two things per resource:
  release  how much of its stock to use today (fraction 0-1). This is how
           agents learn to ration stock across the week.
  split    a score for every district; a softmax over reachable districts turns
           the scores into shares of today's release. Rescue teams are always
           fully released (they are not used up).

Dispatch (shared "needs board"): shipments go out nearest-first and no district
gets more than it still needs today; anything not needed stays in stock.
Trucks: if a centre's plan needs more truckloads than it has, it is scaled down.

Reward (shared by all agents, every day):
    r = coverage + alpha * vulnerability-weighted coverage - beta * Gini
        - delta * average delivery hours / 10
coverage is the simulator's daily score; the other terms use each district's
coverage ratio that day (mean over resources).
"""
from collections import defaultdict

import numpy as np

from ml.env.metrics import gini
from ml.env.relief_env import CONSUMABLES, RESOURCES, TRUCKLOAD

R = len(RESOURCES)
NC = len(CONSUMABLES)
UNIT = np.array([TRUCKLOAD[r] for r in CONSUMABLES] + [1.0])
G_DIM, A_DIM, DR_DIM, P_DIM = 11, 9, 8, 6


class MultiAgentRelief:
    def __init__(self, env, alpha=0.5, beta=1.0, delta=0.05):
        self.env = env
        self.alpha, self.beta, self.delta = alpha, beta, delta
        self.centres = [c["centre_id"] for c in env.centres]
        self.home = {c["centre_id"]: c["district"] for c in env.centres}
        self.districts = env.districts
        self.vuln = np.array([env.vulnerability[d] for d in self.districts])
        self.trucks = np.array([int(c["vehicles"]) * 2 for c in env.centres], dtype=float)

    # --------------------------------------------------------------- features
    def reset(self, seed=None):
        self.obs = self.env.reset(seed)
        self.init_stock = self._stock_array()
        return self.features()

    def _stock_array(self):
        s = self.obs["stock"]
        return np.array([[s[c][r] for r in RESOURCES] for c in self.centres])

    def features(self):
        o, C, D = self.obs, len(self.centres), len(self.districts)
        stock = self._stock_array()                                          # C x R
        dem = np.array([[o["demand"][d][r] for r in RESOURCES] for d in self.districts])  # D x R
        sev = np.array([o["severity"].get(d, 0.0) for d in self.districts])
        travel = np.array([[o["travel"][(c, d)] if o["travel"][(c, d)] is not None else np.nan
                            for d in self.districts] for c in self.centres])  # C x D
        reach = ~np.isnan(travel)
        fc = np.array([o["forecast_remaining"][r] for r in RESOURCES])
        tot_stock, tot_dem = stock.sum(0), dem.sum(0)
        day_i = len(self.env.days) - o["days_left"]

        loads_needed = (tot_dem[:NC] / UNIT[:NC]).sum()
        g = np.concatenate([
            [day_i / 6, o["days_left"] / 7],
            np.clip(tot_stock[:NC] / np.maximum(tot_dem[:NC], 1e-6), 0, 5) / 5,
            np.clip(tot_stock[:NC] / np.maximum(fc[:NC], 1e-6), 0, 2) / 2,
            [np.clip(tot_stock[3] / max(tot_dem[3], 1.0), 0, 3) / 3,
             np.clip(self.trucks.sum() / max(loads_needed, 1e-6), 0, 3) / 3,
             np.clip(tot_dem[:NC].sum() / np.maximum(fc[:NC], 1e-6).sum() * o["days_left"] / 3, 0, 3) / 3],
        ])
        own_loads = (stock[:, :NC] / UNIT[:NC]).sum(1)
        a = np.column_stack([
            stock[:, :NC] / np.maximum(self.init_stock[:, :NC], 1e-6),
            np.clip(stock[:, :NC] / np.maximum(tot_stock[:NC], 1e-6) * C / 3, 0, 3),
            np.log1p(own_loads / self.trucks) / 2,
            self.trucks / self.trucks.mean() / 2,
            np.clip(stock[:, 3] / max(tot_stock[3], 1e-6) * C / 3, 0, 3),
        ])
        share = dem / np.maximum(tot_dem, 1e-6) * D / 4                      # D x R
        dr = np.zeros((D, R, DR_DIM))
        dr[..., 0] = np.clip(share, 0, 3)
        dr[..., 1] = np.log1p(dem / UNIT) / 5
        dr[..., 2] = sev[:, None]
        dr[..., 3] = self.vuln[:, None]
        dr[..., 4:] = np.eye(R)[None]

        tt = np.nan_to_num(travel, nan=0.0)
        rank = np.zeros((C, D))
        for j in range(D):
            order = np.argsort(np.where(reach[:, j], tt[:, j], np.inf))
            rank[order, j] = np.arange(C)
        own = np.array([[self.home[c] == d for d in self.districts] for c in self.centres], float)
        p = np.zeros((C, D, R, P_DIM))
        p[..., 0] = reach[:, :, None]
        p[..., 1] = (tt / 10)[:, :, None]
        p[..., 2] = own[:, :, None]
        p[..., 3] = (np.where(reach, rank, C) / C)[:, :, None]
        p[..., 4] = (reach.sum(0) / C)[None, :, None]
        p[..., 5] = np.clip(np.log1p(stock[:, None, :] / np.maximum(dem[None], 1e-6)), 0, 3) / 3
        mask = np.repeat(reach[:, :, None], R, axis=2)                       # C x D x R

        critic = np.concatenate([g, np.column_stack([share, sev, self.vuln]).ravel(),
                                 a[:, :NC].ravel()])
        self._cache = dict(stock=stock, dem=dem, travel=tt, reach=reach)
        return dict(g=g.astype(np.float32), a=a.astype(np.float32), dr=dr.astype(np.float32),
                    p=p.astype(np.float32), mask=mask, critic=critic.astype(np.float32))

    # ----------------------------------------------------------------- acting
    def to_shipments(self, release, weights):
        """release: C x NC fractions; weights: C x D x R shares (rows sum to 1)."""
        st, dem, tt, reach = (self._cache[k] for k in ("stock", "dem", "travel", "reach"))
        rel = np.concatenate([release, np.ones((len(self.centres), 1))], axis=1)
        amt = (rel * st)[:, None, :] * weights * reach[:, :, None]           # C x D x R
        loads = (amt[:, :, :NC] / UNIT[:NC]).sum((1, 2))
        scale = np.minimum(1.0, self.trucks / np.maximum(loads, 1e-9))
        amt[:, :, :NC] *= scale[:, None, None]
        # needs board: nearest centre first, never more than the district needs
        for j in range(len(self.districts)):
            order = np.argsort(np.where(reach[:, j], tt[:, j], np.inf))
            for r in range(R):
                need = dem[j, r]
                for i in order:
                    give = min(amt[i, j, r], need)
                    amt[i, j, r] = give
                    need -= give
        ship = {}
        for i, c in enumerate(self.centres):
            for j, d in enumerate(self.districts):
                for k, r in enumerate(RESOURCES):
                    if amt[i, j, k] > 1e-6:
                        ship[(c, d, r)] = float(amt[i, j, k])
        return ship

    def step(self, release, weights):
        ship = self.to_shipments(release, weights)
        self.obs, score, done, rec = self.env.step(ship)
        parts = self.reward_parts(rec, score)
        r = parts["coverage"] + self.alpha * parts["vuln_cov"] - self.beta * parts["gini"] \
            - self.delta * parts["delay"] / 10
        return (None if done else self.features()), r, done, parts

    def reward_parts(self, rec, score):
        ratios = defaultdict(list)
        for row in rec["rows"]:
            if row["demand"] > 0:
                ratios[row["district"]].append(row["covered"] / row["demand"])
        cov = {d: np.mean(v) for d, v in ratios.items()}
        w = {d: 1 + self.env.vulnerability[d] for d in cov}
        vw = sum(w[d] * cov[d] for d in cov) / max(sum(w.values()), 1e-9)
        return {"coverage": score, "vuln_cov": vw, "gini": gini(list(cov.values())),
                "delay": rec["avg_delay_hr"]}
