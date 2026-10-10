"""Baseline allocation policies for the relief simulator (Step 3).

All policies plan one day at a time from the current observation and return
{(centre_id, district, resource): amount}. They see the day's demand,
severity, stock, truck capacity and which roads are open.

  LocalFirst      each centre serves its own district, then the nearest ones
  GreedySeverity  districts in order of GAT severity; each filled from the
                  nearest centres with stock
  LPEfficient     OR-Tools linear program: maximise total coverage today,
                  small penalty on travel time
  LPFair          same LP plus vulnerability/severity weights and a max-min
                  term that raises the worst-covered district
"""
from ortools.linear_solver import pywraplp

from ml.env.relief_env import CONSUMABLES, RESOURCES, TRUCKLOAD


class _Ledger:
    """Tracks remaining stock and trucks while a greedy policy plans a day."""
    def __init__(self, obs):
        self.stock = {c: dict(s) for c, s in obs["stock"].items()}
        self.trucks = dict(obs["trucks"])
        self.teams_free = {c: s["rescue_teams"] for c, s in obs["stock"].items()}
        self.plan = {}

    def send(self, c, d, r, want):
        if r == "rescue_teams":
            amt = min(want, self.teams_free[c])
            self.teams_free[c] -= amt
        else:
            amt = min(want, self.stock[c][r], self.trucks[c] * TRUCKLOAD[r])
            self.stock[c][r] -= amt
            self.trucks[c] -= amt / TRUCKLOAD[r]
        if amt > 0:
            self.plan[(c, d, r)] = self.plan.get((c, d, r), 0) + amt
        return amt


def _fill(ledger, obs, d, r, need):
    centres = sorted((t, c) for (c, dd), t in obs["travel"].items() if dd == d and t is not None)
    for _, c in centres:
        if need <= 1e-9:
            break
        need -= ledger.send(c, d, r, need)


class LocalFirst:
    name = "Local-first (nearest centre)"

    def __call__(self, obs):
        L = _Ledger(obs)
        remaining = {d: dict(v) for d, v in obs["demand"].items()}
        for c, home in obs["centre_district"].items():
            order = sorted((t, d) for (cc, d), t in obs["travel"].items() if cc == c and t is not None)
            for _, d in order:
                for r in RESOURCES:
                    remaining[d][r] -= L.send(c, d, r, remaining[d][r])
        return L.plan


class GreedySeverity:
    name = "Greedy by severity"

    def __call__(self, obs):
        L = _Ledger(obs)
        order = sorted(obs["demand"], key=lambda d: -obs["severity"].get(d, 0))
        for d in order:
            for r in RESOURCES:
                _fill(L, obs, d, r, obs["demand"][d][r])
        return L.plan


class LPEfficient:
    name = "LP: max coverage (OR-Tools)"
    fair = False

    def __call__(self, obs):
        # Work in truckloads (teams for rescue) so coefficients stay in a similar
        # range; litres of water would otherwise make the LP numerically unstable.
        unit = {r: TRUCKLOAD.get(r, 1.0) for r in RESOURCES}
        dem = {d: {r: v[r] / unit[r] for r in RESOURCES} for d, v in obs["demand"].items()}
        stock = {c: {r: v[r] / unit[r] for r in RESOURCES} for c, v in obs["stock"].items()}
        s = pywraplp.Solver.CreateSolver("GLOP")
        centres, districts = list(stock), list(dem)
        reach = [(c, d) for (c, d), t in obs["travel"].items() if t is not None]
        x = {(c, d, r): s.NumVar(0, s.infinity(), "") for c, d in reach for r in RESOURCES}
        total = {r: sum(dem[d][r] for d in districts) or 1.0 for r in RESOURCES}
        cov = {}
        for d in districts:
            for r in RESOURCES:
                cov[d, r] = s.NumVar(0, dem[d][r], "")
                s.Add(cov[d, r] <= sum(x[c, d, r] for c in centres if (c, d, r) in x))
        for c in centres:
            for r in RESOURCES:
                s.Add(sum(x[c, d, r] for d in districts if (c, d, r) in x) <= stock[c][r])
            s.Add(sum(x[c, d, r] for d in districts for r in CONSUMABLES if (c, d, r) in x)
                  <= obs["trucks"][c])
        all_trucks = sum(obs["trucks"].values()) or 1.0
        travel_pen = sum(obs["travel"][c, d] * x[c, d, r] for (c, d, r) in x
                         if r in CONSUMABLES) / (all_trucks * 10)
        obj = sum(self.weight(obs, d) * cov[d, r] / total[r] for d in districts for r in RESOURCES)
        if self.fair:
            # Per-district coverage ratios, weighted by vulnerability and severity, so
            # small or remote districts count as much as large ones.
            n = sum(1 for d in districts for r in RESOURCES if dem[d][r] > 1e-9) or 1
            obj = 0.5 * obj + len(RESOURCES) * sum(
                self.weight(obs, d) * cov[d, r] * (1 / dem[d][r])
                for d in districts for r in RESOURCES if dem[d][r] > 1e-9) / n
            z = s.NumVar(0, 1, "z")
            for d in districts:
                for r in RESOURCES:
                    if dem[d][r] > 1e-9:
                        s.Add(z * dem[d][r] <= cov[d, r])
            obj = obj + len(RESOURCES) * z
        s.Maximize(obj - 0.01 * travel_pen)
        status = s.Solve()
        if status != pywraplp.Solver.OPTIMAL:
            raise RuntimeError(f"LP not solved (status {status}) on day {obs['day']}")
        return {(c, d, r): v.solution_value() * unit[r]
                for (c, d, r), v in x.items() if v.solution_value() > 1e-7}

    def weight(self, obs, d):
        return 1.0


class LPFair(LPEfficient):
    name = "LP: fairness-aware (OR-Tools)"
    fair = True

    def weight(self, obs, d):
        return (1 + obs["vulnerability"][d]) * (0.5 + obs["severity"].get(d, 0))


ALL = [LocalFirst, GreedySeverity, LPEfficient, LPFair]
