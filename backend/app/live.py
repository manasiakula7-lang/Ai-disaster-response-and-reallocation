"""Live operations: the Step 6 reallocation loop run event by event behind the API.

A live session replays the official flood week on a clock that the dashboard
advances. Two kinds of crisis reports arrive:

  replay   the real HumAID tweets of 18-24 Aug 2018 (the 449 that Step 6 uses),
           at their real posting time. As in Step 6, each one moves the planner's
           estimate of that district's need halfway to the true value.
  manual   a report typed into the dashboard (a field officer's message). It goes
           through the Step 1 NLP live (classifier, needs, urgency, gazetteer),
           and the people it mentions become new need in that district: added to
           the simulator's true demand and to the planner's estimate. Because the day's
           budget was fixed in the morning, the same amount is released from the
           reserve stock of the nearest centres that can still reach the district.

After every report or road change the next dispatch wave is re-planned with the
stock left, and the change against the previous plan is logged, so the dashboard
can show what each report moved. Trucks leave at 06:00, 12:00, 18:00 and 24:00
exactly as in Step 6; the last wave closes the day in the simulator.
"""
import math
import random
import re
import threading
import uuid
from collections import defaultdict

from ml.env.metrics import episode_metrics
from ml.env.relief_env import CONSUMABLES, RESOURCES, ROOT, TRUCKLOAD
from ml.marl.scenarios import ScenarioEnv
from ml.nlp.gazetteer import find_districts
from ml.nlp.needs import find_resources, urgency_score
from ml.realloc.loop import (FORECAST_SD, REPORT_PULL, RESOURCE_MAP, WAVES, LPPlanner, MappoPlanner,
                             apply_road_event, load_reports, road_times, travel_from)
from backend.app.sim import summarise

MODEL = ROOT / "ml" / "nlp" / "models" / "tweet_classifier.joblib"
# Per person, from data/simulated/demand_timeline.csv (food = people/4, water = 15 L, medicine = people/50).
PER_PERSON = {"food_kits": 0.25, "water_litres": 15.0, "medicine_kits": 0.02}
MIN_CHANGE = {"food_kits": 10, "water_litres": 250, "medicine_kits": 2, "rescue_teams": 0.5}
PEOPLE = re.compile(r"(\d[\d,]*)\s*\+?\s*(people|persons|person|members|families|family|children|kids|"
                    r"villagers|residents|houses|homes|households|patients|elderly|students)", re.I)
FAMILY_OF = re.compile(r"family of (\d+)", re.I)
MAX_EVENTS = 2000

_classifier = None


def classifier():
    # Imported here so the API still starts if scikit-learn is missing; only field reports need it.
    global _classifier
    if _classifier is None:
        try:
            import joblib
        except ImportError as e:
            raise RuntimeError("scikit-learn is not installed: run pip install -r backend/requirements.txt") from e
        _classifier = joblib.load(MODEL)
    return _classifier


def people_mentioned(text):
    """Rough head count from the text: '30 families' -> 120, 'family of 5' -> 5."""
    total = 0
    for n, unit in PEOPLE.findall(text):
        n = int(n.replace(",", ""))
        total += n * 4 if unit.lower() in ("families", "family", "houses", "homes", "households") else n
    total += sum(int(n) for n in FAMILY_OF.findall(text))
    return min(total, 20000)


def analyse(text, district=None):
    """Step 1 NLP on one message: category, confidence, needs, urgency, district."""
    from ml.nlp.extract_reports import ACTIONABLE
    from ml.nlp.train_classifier import clean
    model = classifier()
    p = model.predict_proba([clean(text)])[0]
    i = p.argmax()
    label, conf = str(model.classes_[i]), float(p[i])
    found = find_districts(text)
    needs = find_resources(text, label)
    urgency = urgency_score(text, label, conf)
    return {"category": label, "confidence": round(conf, 3), "urgency": urgency, "needs": needs,
            "districts_found": found, "district": district or (found[0] if found else None),
            "district_source": "chosen" if district else ("text" if found else None),
            "people": people_mentioned(text), "actionable": label in ACTIONABLE or bool(needs)}


def _hhmm(hour):
    h = int(hour); m = int(round((hour - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h:02d}:{m:02d}"


class LiveSession:
    def __init__(self, policy="mappo"):
        self.id = uuid.uuid4().hex[:8]
        self.policy = policy
        self.lock = threading.Lock()
        self.env = ScenarioEnv()
        self.planner = MappoPlanner(self.env) if policy == "mappo" else LPPlanner()
        self.reports = load_reports()
        self.rtimes = road_times(self.env)
        self.obs = self.env.reset(None)
        self.frng = random.Random(499)          # same forecast noise as Step 6 on the official week
        self.base_tt = {int(e["edge_id"]): float(e["travel_time_hr"]) for e in self.env.edges}
        self.known_roads = {k: ("open", t) for k, t in self.base_tt.items()}
        self.events, self.seq = [], 0
        self.done = False
        self.hour = 0.0
        self.counts = defaultdict(int)
        self.days = []                          # per finished day: need met and worst district
        self._start_day()

    # ------------------------------------------------------------ day state
    def _start_day(self):
        obs, env = self.obs, self.env
        self.day = obs["day"]
        self.truth = obs["demand"]              # the simulator's dict: manual reports add to it
        self.est = {d: {r: v[r] * math.exp(self.frng.gauss(0, FORECAST_SD)) for r in RESOURCES}
                    for d, v in self.truth.items()}
        self.forecast = {d: dict(v) for d, v in self.est.items()}
        self.roads = dict(self.known_roads)
        self.queue = sorted([(self.rtimes[(self.day, int(e["edge_id"]))], "road", e)
                             for e in env.events.get(self.day, [])] +
                            [(x[0], "report", x) for x in self.reports.get(self.day, [])], key=lambda x: x[0])
        self.qi = 0
        self.travel = travel_from(env, self.roads)
        self.sent = defaultdict(float)
        self.teams_used = defaultdict(float)
        self.trucks = {c: n / len(WAVES) for c, n in obs["trucks"].items()}
        self.stock = {c: dict(s) for c, s in obs["stock"].items()}
        self.budget = self.planner.budget({**obs, "demand": self.est, "travel": self.travel})
        self.shipments = defaultdict(float)
        self.wave_i = 0
        self.hour = 0.0
        self.plan = self._plan(commit=False)
        self._log("day", "", f"Day {self.day} starts: morning forecast of need, roads as known last night")

    def _plan(self, commit):
        """Plan the next wave with what is known now. commit=True sends it."""
        budget = self.budget if commit else {c: dict(v) for c, v in self.budget.items()}
        stock = self.stock if commit else {c: dict(v) for c, v in self.stock.items()}
        teams = self.teams_used if commit else defaultdict(float, self.teams_used)
        remaining = {d: {r: max(0.0, self.est[d][r] - self.sent[d, r]) for r in RESOURCES} for d in self.est}
        w_obs = {**self.obs, "demand": remaining, "travel": self.travel, "trucks": self.trucks,
                 "stock": {c: {**{r: stock[c][r] for r in CONSUMABLES},
                               "rescue_teams": stock[c]["rescue_teams"] - teams[c]} for c in stock}}
        raw = self.planner.allocate(w_obs, budget)
        out = {}
        for (c, d, r), amt in raw.items():
            amt = float(amt)                      # planners may return numpy floats
            if self.travel.get((c, d)) is None or amt <= 0:
                continue
            if r == "rescue_teams":
                amt = float(min(amt, stock[c][r] - teams[c])); teams[c] += amt
            else:
                amt = float(min(amt, budget[c][r], stock[c][r]))
                budget[c][r] -= amt; stock[c][r] -= amt
            if amt > 1e-6:
                out[(c, d, r)] = amt
                if commit:
                    self.sent[d, r] += amt
                    self.shipments[(c, d, r)] += amt
        return out

    def _replan(self, reason_seq):
        old, self.plan = self.plan, self._plan(commit=False)
        changes = []
        for k in set(old) | set(self.plan):
            a, b = old.get(k, 0.0), self.plan.get(k, 0.0)
            if abs(b - a) >= MIN_CHANGE[k[2]]:
                changes.append({"centre": k[0], "district": k[1], "resource": k[2],
                                "before": round(a, 1), "after": round(b, 1)})
        changes.sort(key=lambda x: -abs(x["after"] - x["before"]) / MIN_CHANGE[x["resource"]])
        by_district = defaultdict(lambda: defaultdict(float))
        for x in changes:
            by_district[x["district"]][x["resource"]] += x["after"] - x["before"]
        return {"wave": _hhmm(WAVES[self.wave_i]), "changes": changes[:12], "n_changes": len(changes),
                "by_district": {d: dict(v) for d, v in by_district.items()}, "cause": reason_seq}

    # --------------------------------------------------------------- events
    def _log(self, kind, district, detail, **extra):
        self.seq += 1
        e = {"seq": self.seq, "day": self.day, "time": _hhmm(self.hour), "type": kind,
             "district": district, "detail": detail, **extra}
        self.events.append(e)
        self.counts[kind] += 1
        del self.events[:-MAX_EVENTS]
        return e

    def _pull(self, d, resources):
        """Step 6 rule: a report moves the estimate halfway to the truth. Returns big jumps."""
        jumps = []
        for r in resources:
            old = self.est[d][r]
            self.est[d][r] += REPORT_PULL * (self.truth[d][r] - self.est[d][r])
            if old > 0 and abs(self.est[d][r] - old) / old >= 0.3:
                jumps.append(f"need estimate for {r} changed {old:.0f} -> {self.est[d][r]:.0f}")
        return jumps

    def _handle(self, kind, payload):
        if kind == "road":
            apply_road_event(self.env, self.roads, payload)
            self.travel = travel_from(self.env, self.roads)
            e = self._log(f"road_{payload['status']}", "", f"{payload['source']} - {payload['target']}")
            for d in self.env.districts:
                if all(self.travel[(c, d)] is None for c in self.stock):
                    self._log("alert", d, "cut off: no open road from any centre")
            e["replan"] = self._replan(e["seq"])
        else:
            _, d, res, tid, text = payload
            e = self._log("report", d, text, tweet_id=tid, resources=res, source="replay")
            for j in self._pull(d, res):
                self._log("alert", d, j)
            e["replan"] = self._replan(e["seq"])

    def _wave(self):
        self.hour = WAVES[self.wave_i]
        sent = self._plan(commit=True)
        loads = defaultdict(float)
        for (c, d, r), amt in sent.items():
            if r in TRUCKLOAD:
                loads[d] += amt / TRUCKLOAD[r]
        top = sorted(loads.items(), key=lambda kv: -kv[1])[:3]
        self._log("dispatch", "", f"{sum(loads.values()):.0f} truckloads to {len(loads)} districts; most to " +
                  ", ".join(f"{d} ({v:.0f})" for d, v in top),
                  shipments=[{"centre": c, "district": d, "resource": r, "amount": round(a, 1)}
                             for (c, d, r), a in sent.items()])
        self.wave_i += 1
        if self.wave_i < len(WAVES):
            self.plan = self._plan(commit=False)
            return
        # 24:00: close the day in the simulator, then start the next one
        for _, kind, payload in self.queue:
            if kind == "road":
                apply_road_event(self.env, self.known_roads, payload)
        self.obs, _, self.done, rec = self.env.step(dict(self.shipments))
        cov = {}
        for d in self.env.districts:
            rows = [x for x in rec["rows"] if x["district"] == d and x["demand"] > 0]
            cov[d] = sum(x["covered"] / x["demand"] for x in rows) / len(rows) if rows else 1.0
            if self.env.severity.get(rec["day"], {}).get(d, 0) >= 0.3 and cov[d] < 0.25:
                self._log("alert", d, f"neglected: only {cov[d]:.0%} of need met today")
        worst = min(cov, key=cov.get)
        met = _day_met(rec)
        self.days.append({"day": rec["day"], "met": float(met), "worst": float(cov[worst]), "worst_district": worst,
                          "truckloads": float(rec["loads"]), "delay": float(rec["avg_delay_hr"])})
        self._log("day_end", "", f"Day {rec['day']} closed: {met:.0%} of need met, worst-off {worst} ({cov[worst]:.0%})")
        if not self.done:
            self._start_day()

    def advance(self, hours=None, until=None):
        """Move the clock forward. until='event' stops after the next report/road/wave."""
        with self.lock:
            start = self.seq
            target = self.hour + (hours or 0) if until != "event" else 99
            while not self.done:
                next_ev = self.queue[self.qi][0] if self.qi < len(self.queue) else 99
                next_wave = WAVES[self.wave_i]
                t = min(next_ev, next_wave)
                if t > target:
                    break
                if next_ev <= next_wave:
                    self.hour = next_ev
                    _, kind, payload = self.queue[self.qi]; self.qi += 1
                    self._handle(kind, payload)
                else:
                    day_before = self.day
                    self._wave()
                    if self.day != day_before:          # a new day began at 00:00
                        target -= 24
                if until == "event":
                    break
            if not self.done and until != "event":
                self.hour = max(self.hour, min(target, 24.0))
            return self.since(start)

    def submit(self, text, district=None):
        """A new report typed into the dashboard."""
        with self.lock:
            if self.done:
                raise ValueError("the week is over; start a new live session")
            a = analyse(text, district)
            d = a["district"]
            if d is None:
                a["outcome"] = "not placed: no Kerala place name found; choose a district and send again"
                e = self._log("manual", "", text, nlp=a, source="manual")
                return {"event": e, "nlp": a}
            if not a["actionable"]:
                a["outcome"] = "not actionable: no need found, so the plan is unchanged"
                e = self._log("manual", d, text, nlp=a, source="manual")
                return {"event": e, "nlp": a}
            resources = sorted({x for k in a["needs"] for x in RESOURCE_MAP.get(k, [])}) or list(CONSUMABLES)
            people = a["people"] or int(50 + 450 * a["urgency"])
            added = {}
            for r in resources:
                extra = people * PER_PERSON[r] if r in PER_PERSON else max(1.0, round(people / 500))
                self.truth[d][r] += extra
                # new need on top of what is already on its way, even if earlier waves over-sent
                self.est[d][r] = max(self.est[d][r], self.sent[d, r]) + extra
                added[r] = round(extra, 1)
            a["released"] = self._release(d, added)
            a["people_used"] = people
            a["people_source"] = "text" if a["people"] else "urgency"
            a["added_need"] = added
            a["outcome"] = "plan updated"
            e = self._log("manual", d, text, nlp=a, source="manual", resources=resources)
            if a["urgency"] >= 0.7:
                self._log("alert", d, f"urgent field report: about {people} people need "
                          + ", ".join(r.replace("_", " ") for r in resources))
            e["replan"] = self._replan(e["seq"])
            return {"event": e, "nlp": a}

    def _release(self, d, added):
        """Emergency release: the day's budget was fixed in the morning, so stock for a new need
        comes from the reserve of centres with an open road to d, nearest first."""
        released = {}
        reach = sorted((c for c in self.stock if self.travel.get((c, d)) is not None),
                       key=lambda c: self.travel[(c, d)])
        for r, extra in added.items():
            if r not in CONSUMABLES:
                continue
            left = extra
            for c in reach:
                spare = self.stock[c][r] - self.budget[c][r]
                take = max(0.0, min(left, spare))
                self.budget[c][r] += take
                left -= take
                if left <= 1e-6:
                    break
            released[r] = round(extra - left, 1)
        return released

    # ----------------------------------------------------------------- views
    def since(self, seq):
        return [e for e in self.events if e["seq"] > seq]

    def state(self):
        with self.lock:
            districts = {}
            for d in self.env.districts:
                rs = [r for r in RESOURCES if self.truth[d][r] > 0]
                cov = (sum(min(1.0, self.sent[d, r] / self.truth[d][r]) for r in rs) / len(rs)) if rs else 1.0
                planned = defaultdict(float)
                for (c, dd, r), a in self.plan.items():
                    if dd == d:
                        planned[r] += a
                districts[d] = {"need": {r: round(self.truth[d][r], 1) for r in RESOURCES},
                                "estimate": {r: round(self.est[d][r], 1) for r in RESOURCES},
                                "forecast": {r: round(self.forecast[d][r], 1) for r in RESOURCES},
                                "sent": {r: round(self.sent[d, r], 1) for r in RESOURCES},
                                "next_wave": {r: round(planned[r], 1) for r in RESOURCES},
                                "coverage_so_far": round(cov, 4)}
            stock = {r: float(sum(s[r] for s in self.stock.values())) for r in RESOURCES}
            init = {r: float(sum(s[r] for s in self.env.initial_stock.values())) for r in RESOURCES}
            return {"session_id": self.id, "policy": self.policy, "done": self.done, "day": self.day,
                    "time": _hhmm(self.hour), "hour": self.hour,
                    "next_wave": None if self.done else _hhmm(WAVES[self.wave_i]),
                    "next_event": None if self.done or self.qi >= len(self.queue) else _hhmm(self.queue[self.qi][0]),
                    "reports_left_today": sum(1 for x in self.queue[self.qi:] if x[1] == "report"),
                    "counts": dict(self.counts), "districts": districts,
                    "plan": [{"centre": c, "district": d, "resource": r, "amount": round(a, 1)}
                             for (c, d, r), a in self.plan.items()],
                    "roads": {str(k): "blocked" if st == "blocked" else
                              ("slowed" if tt > self.base_tt[k] + 1e-6 else "open")
                              for k, (st, tt) in self.roads.items()},
                    "stock_left": stock, "stock_start": init, "days": self.days,
                    "metrics": summarise(episode_metrics(self.env)) if self.env.log else None,
                    "last_seq": self.seq}


def _day_met(rec):
    tot = defaultdict(lambda: [0.0, 0.0])
    for row in rec["rows"]:
        tot[row["resource"]][0] += row["covered"]; tot[row["resource"]][1] += row["demand"]
    ratios = [c / d for c, d in tot.values() if d > 0]
    return sum(ratios) / len(ratios) if ratios else 1.0


LIVE: dict[str, LiveSession] = {}
